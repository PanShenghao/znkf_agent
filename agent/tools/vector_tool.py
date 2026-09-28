"""
文件职能: 商品咨询的「查文档」工具 —— 混合检索（BM25 关键词 + 向量语义，RRF 融合）+ 父子分块（检索 child、返回 parent）。
与入库（core/rag）共用同一套 加载/清洗/分块，保证 BM25 索引与 Milvus 向量一致。
"""
import os

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.tools import tool
from rank_bm25 import BM25Okapi
import jieba

from config import get_settings
from core.grounding import record_evidence
from core.rag import list_supported_files, load_document, clean_text, chunk_document, COLLECTION_NAME
from core.rag.indexer import _chunk_id

# 向量相似度（COSINE）低于该值视为「无可靠证据」
RAG_CONFIDENCE_THRESHOLD = 0.3

# demo_data 的绝对路径
DEMO_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'demo_data')

# 单例缓存
_milvus_client = None
_embeddings = None
_local_chunks = None       # [{chunk_id, content, parent_text, source}]
_chunk_id_to_idx = {}
_bm25 = None


def _get_milvus_client():
    global _milvus_client
    if _milvus_client is None:
        from pymilvus import MilvusClient
        s = get_settings()
        _milvus_client = MilvusClient(uri=f"http://{s.milvus_host}:{s.milvus_port}")
    return _milvus_client


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        s = get_settings()
        _embeddings = DashScopeEmbeddings(model="text-embedding-v2", dashscope_api_key=s.dashscope_api_key)
    return _embeddings


def _get_local_chunks():
    """用与入库一致的 loader/cleaner/chunker 加载并分块，建 BM25 索引（单例）。"""
    global _local_chunks, _chunk_id_to_idx, _bm25
    if _bm25 is not None:
        return _local_chunks
    _local_chunks = []
    for f in list_supported_files(DEMO_DATA_DIR):
        doc_id = f.name
        text = clean_text(load_document(f))
        for c in chunk_document(text):
            _local_chunks.append({
                "chunk_id": _chunk_id(doc_id, c["parent_id"], c["content"]),
                "content": c["content"],
                "parent_text": c["parent_text"],
                "source": f.name,
            })
    _chunk_id_to_idx = {c["chunk_id"]: i for i, c in enumerate(_local_chunks)}
    tokenized = [list(jieba.cut(c["content"])) for c in _local_chunks]
    _bm25 = BM25Okapi(tokenized)
    return _local_chunks


def _vector_search(query: str, top_k: int):
    """向量召回，返回 (chunk_id 列表, top-1 COSINE 相似度)。"""
    client = _get_milvus_client()
    if not client.has_collection(COLLECTION_NAME):
        return [], 0.0
    try:
        vec = _get_embeddings().embed_query(query)
        results = client.search(
            collection_name=COLLECTION_NAME, data=[vec], limit=top_k,
            output_fields=["chunk_id"],
        )
    except Exception:
        return [], 0.0
    hits = results[0] if results else []
    ids = [h["entity"]["chunk_id"] for h in hits if h.get("entity", {}).get("chunk_id")]
    top_score = float(hits[0]["distance"]) if hits else 0.0  # COSINE：越大越相似
    return ids, top_score


def _hybrid_search(query: str, top_k: int = 3, recall_k: int = 20):
    """混合检索：向量 + BM25 各召回 recall_k 个候选，RRF 融合后取 top-k parent（去重）。"""
    chunks = _get_local_chunks()
    vec_ids, top_confidence = _vector_search(query, recall_k)

    query_tokens = list(jieba.cut(query))
    bm25_scores = _bm25.get_scores(query_tokens)
    bm25_ranked = sorted(range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True)[:recall_k]

    rrf = {}
    for rank, cid in enumerate(vec_ids, 1):
        rrf[cid] = rrf.get(cid, 0) + 1.0 / (60 + rank)
    for rank, idx in enumerate(bm25_ranked, 1):
        cid = chunks[idx]["chunk_id"]
        rrf[cid] = rrf.get(cid, 0) + 1.0 / (60 + rank)

    # 映射到 parent（去重），取前 top_k 个
    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
    seen, parents = set(), []
    for cid, _ in ranked:
        if cid not in _chunk_id_to_idx:
            continue
        meta = chunks[_chunk_id_to_idx[cid]]
        key = (meta["source"], meta["parent_text"])
        if key in seen:
            continue
        seen.add(key)
        parents.append(meta)
        if len(parents) >= top_k:
            break
    return parents, top_confidence


def warmup() -> None:
    """预热：预建 BM25 索引 + 加载 Milvus 集合进内存，避免首个查询冷启动误判「无证据」。"""
    try:
        _get_local_chunks()  # 建 BM25
        client = _get_milvus_client()
        if client.has_collection(COLLECTION_NAME):
            client.load_collection(COLLECTION_NAME)
    except Exception:
        pass


@tool
def query_vector_db(query: str) -> str:
    """通过混合检索（关键词+语义）查询数码商品的说明文档（RAG）。
    当用户询问商品概念、参数说明、使用教程、政策规则时，使用此工具。
    若返回「[无检索证据]」，必须如实告知用户无法确认，严禁编造。"""
    parents, confidence = _hybrid_search(query, top_k=3, recall_k=20)
    if not parents or confidence < RAG_CONFIDENCE_THRESHOLD:
        record_evidence("vector_db", found=False, score=confidence)
        return ("[无检索证据] 未在文档中检索到可靠的相关信息。"
                "若问题是「有哪些/什么品牌/哪些型号」等关系类问题，请改用 query_knowledge_graph 查询。"
                "否则请如实告知用户无法确认，不要编造。")
    record_evidence("vector_db", found=True, score=confidence)
    parts = [f"[检索置信度: {confidence:.2f}]"]
    for i, p in enumerate(parents, 1):
        parts.append(f"[{i}] 来源:{p['source']}\n{p['parent_text']}")
    return "\n\n".join(parts)

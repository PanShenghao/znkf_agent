"""
文件职能: 向量索引器 —— 分批向量化（防 OOM）+ 增量入库（doc_id 幂等 upsert）+ HNSW 索引。
"""
import hashlib
import logging

from config import get_settings
from .schema import COLLECTION_NAME, EMBEDDING_DIM, BATCH_SIZE

logger = logging.getLogger(__name__)


def _chunk_id(doc_id: str, parent_id: str, content: str) -> str:
    return hashlib.md5(f"{doc_id}:{parent_id}:{content}".encode("utf-8")).hexdigest()


class VectorIndexer:
    def __init__(self, host: str | None = None, port: int | None = None, api_key: str | None = None):
        s = get_settings()
        self._host = host or s.milvus_host
        self._port = port or s.milvus_port
        self._api_key = api_key or s.dashscope_api_key
        self._client = None
        self._embeddings = None

    def _ensure_client(self):
        if self._client is None:
            from pymilvus import MilvusClient
            self._client = MilvusClient(uri=f"http://{self._host}:{self._port}")
        return self._client

    def _ensure_embeddings(self):
        if self._embeddings is None:
            from langchain_community.embeddings import DashScopeEmbeddings
            self._embeddings = DashScopeEmbeddings(model="text-embedding-v2", dashscope_api_key=self._api_key)
        return self._embeddings

    def ensure_collection(self) -> None:
        """建集合（HNSW 索引）。已存在且 schema 匹配则跳过；schema 不匹配则重建。"""
        from pymilvus import DataType

        client = self._ensure_client()
        if client.has_collection(COLLECTION_NAME):
            desc = client.describe_collection(COLLECTION_NAME)
            fields = {f["name"] for f in desc.get("fields", [])}
            if "doc_id" in fields:  # 含 doc_id 说明是新 schema
                return
            # 旧 schema 残留，drop 重建
            client.drop_collection(COLLECTION_NAME)
            logger.warning("集合 %s schema 不匹配，已重建", COLLECTION_NAME)
        schema = client.create_schema(auto_id=False)
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
        schema.add_field("source", DataType.VARCHAR, max_length=256)
        schema.add_field("content", DataType.VARCHAR, max_length=1024)
        schema.add_field("parent_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                               params={"M": 16, "efConstruction": 200})
        client.create_collection(collection_name=COLLECTION_NAME, schema=schema, index_params=index_params)
        logger.info("已创建集合 %s（HNSW 索引）", COLLECTION_NAME)

    def index_document(self, doc_id: str, source: str, chunks: list[dict]) -> int:
        """增量入库：先删该 doc 旧向量，再分批 embed + upsert。返回 chunk 数。"""
        client = self._ensure_client()
        self.ensure_collection()
        self.delete_document(doc_id)  # 幂等：先删旧，避免重复
        if not chunks:
            return 0

        embeddings = self._ensure_embeddings()
        buffered = []
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            vecs = embeddings.embed_documents([c["content"] for c in batch])  # 分批向量化，防 OOM
            for c, vec in zip(batch, vecs):
                buffered.append({
                    "chunk_id": _chunk_id(doc_id, c["parent_id"], c["content"]),
                    "doc_id": doc_id,
                    "source": source,
                    "content": c["content"],
                    "parent_text": c["parent_text"],
                    "embedding": vec,
                })
            client.upsert(collection_name=COLLECTION_NAME, data=buffered)
            buffered = []
        logger.info("入库 %s：%d 个 chunk", source, len(chunks))
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        """按 doc_id 幂等删除某文档的全部向量。"""
        client = self._ensure_client()
        if not client.has_collection(COLLECTION_NAME):
            return
        client.delete(collection_name=COLLECTION_NAME, filter=f'doc_id == "{doc_id}"')

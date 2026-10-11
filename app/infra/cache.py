"""语义缓存：L1 精确匹配 + L2 向量相似匹配，命中直接返回，省 LLM 调用。"""
import logging
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "shop_qa_semantic_cache"   # 电商项目独立集合，避免与云客服冲突
EMBEDDING_DIM = 1536
L1_SEMANTIC_DISTANCE_THRESHOLD = 0.08   # L2 语义命中阈值


class SemanticCache:
    def __init__(self) -> None:
        self._client: Any = None
        self._embeddings: Any = None
        self._available: bool = False

    async def initialize(self) -> None:
        try:
            from pymilvus import MilvusClient
            from langchain_community.embeddings import DashScopeEmbeddings

            s = get_settings()
            self._client = MilvusClient(uri=f"http://{s.milvus_host}:{s.milvus_port}")
            self._embeddings = DashScopeEmbeddings(
                model="text-embedding-v2",
                dashscope_api_key=s.dashscope_api_key,
            )
            self._ensure_collection()
            self._available = True
            logger.info("语义缓存初始化完成")
        except Exception as e:
            logger.warning("语义缓存不可用: %s", e)
            self._available = False

    async def set_cache(self, query: str, response: str, user_id: str | None = None) -> None:
        """把问答对写入缓存"""
        if not self._available:
            return
        normalized = self._normalize(query)
        owner = user_id or ""
        scope = "user" if owner else "public"
        try:
            embedding = await self._embeddings.aembed_query(normalized)
            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[{
                    "question": query.strip(),
                    "question_norm": normalized,
                    "answer": response,
                    "scope": scope,
                    "user_id": owner,
                    "embedding": embedding,
                }],
            )
        except Exception:
            pass

    async def get_cache(self, query: str, user_id: str) -> dict[str, Any] | None:
        """查缓存：先精确匹配，再语义匹配"""
        if not self._available:
            return None
        normalized = self._normalize(query)

        # L1 精确匹配（用户级优先，再全局）
        for scope, filt in [
            ("user", f'question_norm == "{normalized}" and scope == "user" and user_id == "{user_id}"'),
            ("public", f'question_norm == "{normalized}" and scope == "public"'),
        ]:
            hit = self._query_one(filt)
            if hit:
                return {"answer": hit["answer"], "matched_question": hit["question"],
                        "level": "L1_EXACT", "distance": 0.0}

        # L2 语义匹配（向量相似度）
        try:
            embedding = await self._embeddings.aembed_query(normalized)
            results = self._client.search(
                collection_name=COLLECTION_NAME,
                data=[embedding],
                filter=f'scope == "public" or (scope == "user" and user_id == "{user_id}")',
                limit=1,
                output_fields=["question", "answer", "scope", "user_id"],
            )
            if not results or not results[0]:
                return None
            hit = results[0][0]
            distance = float(hit.get("distance", 1.0))
            if distance > L1_SEMANTIC_DISTANCE_THRESHOLD:
                return None
            entity = hit.get("entity", {})
            return {"answer": entity.get("answer", ""), "matched_question": entity.get("question", ""),
                    "level": "L1_SEMANTIC", "distance": distance}
        except Exception:
            return None

    @property
    def available(self) -> bool:
        return self._available

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().lower().split())

    def _query_one(self, filter_expr: str) -> dict[str, Any] | None:
        try:
            rows = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=filter_expr,
                output_fields=["question", "answer", "scope", "user_id"],
                limit=1,
            )
            return rows[0] if rows else None
        except Exception:
            return None

    def _ensure_collection(self) -> None:
        from pymilvus import DataType
        if self._client.has_collection(COLLECTION_NAME):
            return
        schema = self._client.create_schema()
        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("question", DataType.VARCHAR, max_length=2048)
        schema.add_field("question_norm", DataType.VARCHAR, max_length=2048)
        schema.add_field("answer", DataType.VARCHAR, max_length=8192)
        schema.add_field("scope", DataType.VARCHAR, max_length=16)
        schema.add_field("user_id", DataType.VARCHAR, max_length=128)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        index_params = self._client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="IVF_FLAT", metric_type="COSINE", params={"nlist": 256})
        self._client.create_collection(collection_name=COLLECTION_NAME, schema=schema, index_params=index_params)


semantic_cache = SemanticCache()

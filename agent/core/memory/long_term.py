"""
文件职能: 让 Agent 记住用户的「长期偏好」（如「喜欢简洁回答」「经常买苹果产品」），跨会话持久保存，下次对话时按语义检索出来。
"""

import logging

logger = logging.getLogger(__name__)

COLLECTION_NAME = 'long_term_memory'
EMBEDDING_DIM = 1536


class LongTermMemory():
    """
    长期记忆：Milvus 向量库存用户偏好，语义检索 + 按用户隔离
    """

    def __init__(self, host='localhost', port=19530, embedding_api_key=None):
        self._host = host
        self._port = port
        self._embedding_api_key = embedding_api_key
        self._client = None
        self._embeddings = None
        self._available = False

    async def initialize(self):
        try:
            from pymilvus import MilvusClient
            from langchain_community.embeddings import DashScopeEmbeddings

            self._client = MilvusClient(uri=f'http://{self._host}:{self._port}')
            self._embeddings = DashScopeEmbeddings(
                model="text-embedding-v2",
                dashscope_api_key=self._embedding_api_key,
            )
            self._ensure_collection()
            self._available = True

        except Exception:
            self._available = False

    async def save_memory(self, user_id, content, memory_type="general"):
        """
        存一条记忆：文本 → 向量 → 入库
        """
        if not self._available:
            return
        embedding = await self._embeddings.aembed_query(content)
        self._client.insert(
            collection_name=COLLECTION_NAME,
            data=[{
                "user_id": user_id,
                "content": content,
                "memory_type": memory_type,
                "embedding": embedding,
            }]
        )

    async def retrieve_relevant(self, user_id, query, top_k=5):
        """检索最相关的记忆"""
        if not self._available:
            return []
        query_embedding = await self._embeddings.aembed_query(query)
        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[query_embedding],
            filter=f'user_id == "{user_id}"',
            limit=top_k,
            output_fields=["content", "memory_type"],
        )
        memories = []
        for hits in results:
            for hit in hits:
                memories.append(hit["entity"]["content"])
        return memories

    async def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    @property
    def available(self):
        return self._available

    def _ensure_collection(self):
        """ 建集合（类似建表）：定义字段 + 建索引。 """
        from pymilvus import DataType
        if self._client.has_collection(COLLECTION_NAME):
            return
        schema = self._client.create_schema()
        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("user_id", DataType.VARCHAR, max_length=128)
        schema.add_field("content", DataType.VARCHAR, max_length=2048)
        schema.add_field("memory_type", DataType.VARCHAR, max_length=64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        index_params = self._client.prepare_index_params()
        index_params.add_index("embedding", index_type="IVF_FLAT", metric_type="COSINE", params={"nlist": 128})
        self._client.create_collection(collection_name=COLLECTION_NAME, schema=schema, index_params=index_params)

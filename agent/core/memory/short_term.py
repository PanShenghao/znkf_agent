"""
文件职能: 让 Agent 记住「最近几分钟聊了什么」。用 Redis 存对话历史，30 分钟自动过期。
"""
import json
import logging

logger = logging.getLogger(__name__)

COMPRESSION_THRESHOLD = 10   # 超过10条消息就裁剪
DEFAULT_TTL = 1800   # 30分钟过期

class ShortTermMemory:
    """
    短期记忆：Redis 存最近对话，TTL 过期，超长裁剪
    """
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = DEFAULT_TTL):

        self._redis_url = redis_url   # 地址由参数传入
        self._ttl = ttl
        self._client = None
        self._available = False   # 标记redis是否可以用

    async def initialize(self):
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._client.ping()   # ping一下验证连没连上
            self._available = True
        except Exception:
            self._available = False   # 连不上就标记不可用，不崩溃

    async def get_messages(self, user_id, session_id):
        if not self._available:
            return []    # 不可用就返回空列表
        data = await self._client.get(self._key(user_id, session_id))
        return json.loads(data) if data else []

    async def save_messages(self, user_id, session_id, messages):
        if not self._available:
            return
        if len(messages) > COMPRESSION_THRESHOLD:  # 超长先裁剪
            messages = self._trim(messages)
        await self._client.set(
            self._key(user_id, session_id),
            json.dumps(messages, ensure_ascii=False),
            ex=self._ttl,   # 设置过期时间
        )

    async def clear(self, user_id, session_id):
        if self._available:
            await self._client.delete(self._key(user_id, session_id))

    async def close(self):
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass

    @property
    def available(self):          # 对外暴露是否可用
        return self._available

    @staticmethod
    def _key(user_id, session_id):   # 键的设计：按用户+会话隔离
        return f"memory:short:{user_id}:{session_id}"

    @staticmethod
    def _trim(messages):           # 裁剪：保留system+最近6条
        system_msg = [m for m in messages if m.get("role") == "system"]
        other_msg = [m for m in messages if m.get("role") != "system"]
        return system_msg + other_msg[-6:]





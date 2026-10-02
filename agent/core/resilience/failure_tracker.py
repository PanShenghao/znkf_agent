"""
文件职能: 按会话记录「连续失败次数」。多次调用失败 → 达到阈值 → 触发转人工（熔断式升级）。
Redis 优先，Redis 不可用时降级为进程内计数（不崩溃）。
"""
import logging

logger = logging.getLogger(__name__)

_TTL = 1800  # 失败计数 30 分钟过期


class FailureTracker:
    def __init__(self, redis_url: str = "redis://localhost:6379", escalate_threshold: int = 3):
        self._redis_url = redis_url
        self.escalate_threshold = escalate_threshold
        self._client = None
        self._available = False
        self._local: dict = {}

    async def initialize(self) -> None:
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._client.ping()
            self._available = True
        except Exception as e:
            logger.warning("失败计数器 Redis 不可用，降级为进程内计数: %s", e)
            self._available = False

    def _key(self, user_id: str, session_id: str) -> str:
        return f"fail:count:{user_id}:{session_id}"

    async def record_failure(self, user_id: str, session_id: str) -> int:
        """记录一次失败，返回当前连续失败次数。"""
        if self._available:
            try:
                key = self._key(user_id, session_id)
                n = await self._client.incr(key)
                if n == 1:
                    await self._client.expire(key, _TTL)
                return int(n)
            except Exception:
                pass  # 降到进程内
        k = (user_id, session_id)
        self._local[k] = self._local.get(k, 0) + 1
        return self._local[k]

    async def reset(self, user_id: str, session_id: str) -> None:
        if self._available:
            try:
                await self._client.delete(self._key(user_id, session_id))
            except Exception:
                pass
        self._local.pop((user_id, session_id), None)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass

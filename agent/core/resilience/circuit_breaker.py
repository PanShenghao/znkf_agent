"""
文件职能: 熔断器（circuit breaker）—— 依赖连续失败后「打开」，冷却期内短路请求，
避免继续雪崩式打挂下游（LLM provider / MySQL 等）。

状态机：
  CLOSED（正常放行）→ 连续失败达阈值 → OPEN（直接拒绝请求）→ 冷却期满 → HALF_OPEN（放行一个探测）
  → 探测成功回 CLOSED / 探测失败再回 OPEN。

说明：v1 为进程内实现（单 worker 的 uvicorn 已够用）。若未来多 worker 部署，
把 _state 换成 Redis 共享即可（数据结构与方法签名不变）。
"""
import time
import threading
from dataclasses import dataclass
from typing import Dict


class CircuitOpenError(Exception):
    """熔断器打开时抛出：调用方据此走降级 / 转人工分支。"""


@dataclass
class _BreakerState:
    failures: int = 0
    opened_at: float = 0.0
    state: str = "CLOSED"  # CLOSED / OPEN / HALF_OPEN


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = _BreakerState()
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        """请求前调用：是否放行。OPEN 且未过冷却期 → False（上层应直接短路降级）。"""
        with self._lock:
            st = self._state
            if st.state == "CLOSED":
                return True
            if st.state == "OPEN":
                if time.monotonic() - st.opened_at >= self.reset_timeout:
                    st.state = "HALF_OPEN"
                    return True
                return False
            return True  # HALF_OPEN：放行一个探测请求

    def record_success(self) -> None:
        with self._lock:
            self._state.failures = 0
            self._state.state = "CLOSED"

    def record_failure(self) -> None:
        with self._lock:
            st = self._state
            st.failures += 1
            if st.state == "HALF_OPEN" or st.failures >= self.failure_threshold:
                st.state = "OPEN"
                st.opened_at = time.monotonic()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state.state


_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, failure_threshold: int = 3, reset_timeout: float = 60.0) -> CircuitBreaker:
    """按名字获取（单例）熔断器。"""
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name, failure_threshold, reset_timeout)
        return _breakers[name]

"""
文件职能: 结构化日志 + request_id 上下文。
用 contextvar 让同一请求的所有日志带上同一个 request_id，方便生产排查串起整条链路。
"""
import contextvars
import logging
import sys
from typing import Optional

_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    """把当前 contextvar 里的 request_id 注入每条日志记录。"""

    def filter(self, record):
        rid = get_request_id()
        record.request_id = rid if rid else "-"
        return True


_configured = False


def setup_logging(level: str = "INFO") -> None:
    """幂等地配置根 logger（补一个带 request_id 的 handler）。"""
    global _configured
    if _configured:
        return
    # Windows 控制台默认 GBK，中文日志会乱码，统一转 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    fmt = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

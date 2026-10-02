"""
文件职能: RAG 检索证据记录器 —— 反幻觉门的数据来源。

RAG 工具（query_vector_db / query_knowledge_graph）检索时记录「是否找到证据 + 置信度」，
chat_service 在图执行后据此判断：RAG 类问题无证据 → 升级转人工，而不是让模型编造。

实现：按 request_id 隔离（同步工具跑在线程池里，contextvar 写不回来，故用模块级字典 + 锁）。
"""
import threading

from core.logger import get_request_id

_lock = threading.Lock()
_evidence: dict[str, list] = {}


def _rid() -> str:
    return get_request_id() or "global"


def reset_evidence() -> None:
    """每轮开始时清空当前请求的证据记录。"""
    with _lock:
        _evidence.pop(_rid(), None)


def record_evidence(source: str, found: bool, score: float = 0.0) -> None:
    with _lock:
        _evidence.setdefault(_rid(), []).append({"source": source, "found": found, "score": score})


def get_evidence() -> list:
    with _lock:
        return list(_evidence.get(_rid(), []))


def any_found() -> bool:
    """本轮是否检索到过证据。"""
    return any(e["found"] for e in get_evidence())


def best_score() -> float:
    """本轮检索的最高置信度（无记录返回 -1.0）。"""
    ev = get_evidence()
    if not ev:
        return -1.0
    return max(e["score"] for e in ev)

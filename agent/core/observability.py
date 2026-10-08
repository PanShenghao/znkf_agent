"""
文件职能: 可观测 —— token 计量（单价快照）。
用 LangChain callback 记录每次 LLM 调用的 token 用量，按 request_id 聚合，回合结束落库 token_usage 表。
借鉴 ai_customer_service 的「单价快照」：费用按记录时刻的单价算死，调价不追溯历史账单。
"""
import logging
import threading

from langchain_core.callbacks import BaseCallbackHandler

from config import get_settings
from core.logger import get_request_id

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_usage: dict[str, list] = {}

TOKEN_USAGE_DDL = """
CREATE TABLE IF NOT EXISTS token_usage (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    model VARCHAR(64) NOT NULL DEFAULT '',
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    cost DECIMAL(10,6) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='token 用量计费表';
"""


def _rid() -> str:
    return get_request_id() or "global"


def _extract_usage(response) -> dict | None:
    """从 LLMResult 里鲁棒地抽 token 用量（兼容 llm_output.token_usage 与 usage_metadata 两套）。"""
    llm_out = getattr(response, "llm_output", None) or {}
    tu = llm_out.get("token_usage") or llm_out.get("usage")
    if tu:
        return {
            "input_tokens": int(tu.get("prompt_tokens", tu.get("input_tokens", 0)) or 0),
            "output_tokens": int(tu.get("completion_tokens", tu.get("output_tokens", 0)) or 0),
            "total_tokens": int(tu.get("total_tokens", 0) or 0),
            "model": llm_out.get("model_name", ""),
        }
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        um = getattr(msg, "usage_metadata", None)
        if um:
            return {
                "input_tokens": int(getattr(um, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(um, "output_tokens", 0) or 0),
                "total_tokens": int(getattr(um, "total_tokens", 0) or 0),
                "model": getattr(response, "model_name", "") or "",
            }
    except Exception:
        pass
    return None


class TokenUsageCallback(BaseCallbackHandler):
    """记录每个 LLM 调用的 token 用量（线程安全，按 request_id 聚合）。"""

    def on_llm_end(self, response, **kwargs):
        usage = _extract_usage(response)
        if not usage:
            return
        with _lock:
            _usage.setdefault(_rid(), []).append(usage)


def reset_usage() -> None:
    with _lock:
        _usage.pop(_rid(), None)


def aggregate_usage() -> dict | None:
    """聚合本轮所有 LLM 调用的 token 用量 + 费用（单价快照）。无记录返回 None。"""
    rows = list(_usage.get(_rid(), []))
    if not rows:
        return None
    s = get_settings()
    input_tokens = sum(r["input_tokens"] for r in rows)
    output_tokens = sum(r["output_tokens"] for r in rows)
    total = input_tokens + output_tokens
    cost = input_tokens / 1_000_000 * s.llm_input_price_per_1m + output_tokens / 1_000_000 * s.llm_output_price_per_1m
    return {
        "model": rows[0]["model"] or s.model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "cost": round(cost, 6),
    }


def flush_token_usage(user_id: str, session_id: str, agg: dict) -> None:
    """把本轮用量写一条到 token_usage 表（同步，失败只告警）。"""
    import pymysql

    s = get_settings()
    conn = None
    try:
        conn = pymysql.connect(
            host=s.mysql_host, port=s.mysql_port, user=s.mysql_user,
            password=s.mysql_password, database=s.mysql_database,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute(TOKEN_USAGE_DDL)
            cur.execute(
                "INSERT INTO token_usage (user_id, session_id, model, input_tokens, output_tokens, total_tokens, cost) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, session_id, agg["model"], agg["input_tokens"], agg["output_tokens"],
                 agg["total_tokens"], agg["cost"]),
            )
        conn.commit()
    except Exception as e:
        logger.warning("token 用量落库失败: %s", e)
    finally:
        if conn and conn.open:
            conn.close()

"""
文件职能: 工单状态机（tickets + ticket_logs）—— 转人工之后的人工跟进闭环。
借鉴 ai_customer_service：状态机（0待处理 / 1接管中 / 2已取消 / 3已关闭）+ 每次变更写 ticket_logs。

状态流转：
  待处理(0) --接管--> 接管中(1) --关闭--> 已关闭(3)（处理完回流 AI）
  待处理(0) --取消--> 已取消(2)
"""
import logging
import uuid
from enum import IntEnum

import pymysql

from config import get_settings

logger = logging.getLogger(__name__)


class TicketStatus(IntEnum):
    PENDING = 0     # 待处理
    TAKEN = 1       # 接管中（人工已接单）
    CANCELLED = 2   # 已取消
    CLOSED = 3      # 已关闭


TICKETS_DDL = """
CREATE TABLE IF NOT EXISTS tickets (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_no VARCHAR(32) NOT NULL UNIQUE,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    reason VARCHAR(128) NOT NULL,
    context_summary TEXT,
    status TINYINT NOT NULL DEFAULT 0,
    priority TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME NULL,
    INDEX idx_status (status),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工转接工单表';
"""

TICKET_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS ticket_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    action VARCHAR(32) NOT NULL,
    old_status TINYINT NOT NULL,
    new_status TINYINT NOT NULL,
    operator VARCHAR(64) NOT NULL DEFAULT '',
    remark VARCHAR(255) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ticket (ticket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工单操作日志表';
"""


def _get_conn():
    s = get_settings()
    return pymysql.connect(
        host=s.mysql_host,
        port=s.mysql_port,
        user=s.mysql_user,
        password=s.mysql_password,
        database=s.mysql_database,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _new_ticket_no() -> str:
    return "TK-" + uuid.uuid4().hex[:8].upper()


def _ensure_tables(cur) -> None:
    cur.execute(TICKETS_DDL)
    cur.execute(TICKET_LOGS_DDL)


def ensure_ticket_tables() -> None:
    """启动时确保工单表存在（MySQL 未就绪只告警）。"""
    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            _ensure_tables(cur)
        conn.commit()
    except Exception as e:
        logger.warning("初始化工单表失败（MySQL 未就绪？）: %s", e)
    finally:
        if conn and conn.open:
            conn.close()


def _log(cur, ticket_id, action, old_status, new_status, operator="", remark=""):
    cur.execute(
        "INSERT INTO ticket_logs (ticket_id, action, old_status, new_status, operator, remark) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (ticket_id, action, int(old_status), int(new_status), operator, remark),
    )


def create_ticket(user_id: str, session_id: str, reason: str, context_summary: str) -> str | None:
    """新建工单（待处理），写 create 日志，返回 ticket_no；失败返回 None。"""
    conn = None
    ticket_no = _new_ticket_no()
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            _ensure_tables(cur)
            cur.execute(
                "INSERT INTO tickets (ticket_no, user_id, session_id, reason, context_summary, status) "
                "VALUES (%s, %s, %s, %s, %s, 0)",
                (ticket_no, user_id, session_id, reason, context_summary),
            )
            _log(cur, cur.lastrowid, "create", TicketStatus.PENDING, TicketStatus.PENDING, operator="system")
        conn.commit()
        return ticket_no
    except Exception as e:
        logger.error("创建工单失败: %s", e)
        return None
    finally:
        if conn and conn.open:
            conn.close()


def _transition(ticket_no, action, from_statuses, new_status, operator="", remark="") -> bool:
    """状态迁移：仅当当前状态在 from_statuses 内才迁移，并写 ticket_logs。"""
    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM tickets WHERE ticket_no = %s", (ticket_no,))
            row = cur.fetchone()
            if not row:
                logger.warning("工单 %s 不存在", ticket_no)
                return False
            if int(row["status"]) not in {int(s) for s in from_statuses}:
                logger.warning("工单 %s 状态 %s 不允许执行 %s", ticket_no, row["status"], action)
                return False
            if int(new_status) == int(TicketStatus.CLOSED):
                cur.execute("UPDATE tickets SET status=%s, closed_at=NOW() WHERE id=%s", (int(new_status), row["id"]))
            else:
                cur.execute("UPDATE tickets SET status=%s WHERE id=%s", (int(new_status), row["id"]))
            _log(cur, row["id"], action, row["status"], new_status, operator, remark)
        conn.commit()
        return True
    except Exception as e:
        logger.error("工单迁移失败: %s", e)
        return False
    finally:
        if conn and conn.open:
            conn.close()


def takeover_ticket(ticket_no: str, operator: str = "") -> bool:
    """坐席接管：待处理(0) → 接管中(1)。"""
    return _transition(ticket_no, "takeover", {TicketStatus.PENDING}, TicketStatus.TAKEN, operator)


def close_ticket(ticket_no: str, operator: str = "") -> bool:
    """关闭工单：接管中(1) → 已关闭(3)，人工处理完回流 AI。"""
    return _transition(ticket_no, "close", {TicketStatus.TAKEN}, TicketStatus.CLOSED, operator)


def cancel_ticket(ticket_no: str, operator: str = "") -> bool:
    """取消转接：待处理(0) → 已取消(2)。"""
    return _transition(ticket_no, "cancel", {TicketStatus.PENDING}, TicketStatus.CANCELLED, operator)

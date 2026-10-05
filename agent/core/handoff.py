"""
文件职能: 转人工（human handoff）—— 组装 warm handoff 上下文，创建工单（状态机），推送 Chatwoot，返回转接话术。

职责边界：
  - 工单状态机在 core/tickets.py（tickets + ticket_logs）
  - Chatwoot 推送在 core/chatwoot.py
  - 本模块是「转人工」门面：上下文打包 + 工单 + 推送 + 话术
"""
import json
import logging

from langchain_core.messages import AIMessage

from core.workflow.state import AgentState
from core.tickets import create_ticket
from core.chatwoot import get_chatwoot_client

logger = logging.getLogger(__name__)

HANDOFF_BASE = (
    "非常抱歉，您的问题暂时超出了我当前能处理的范围。"
    "已为您记录并转接人工客服，稍后会有专员跟进，请保持联系方式畅通。"
)


def handoff_message(ticket_no: str | None) -> str:
    """转接话术；有工单号则带上，便于用户与坐席对账。"""
    if ticket_no:
        return f"{HANDOFF_BASE}（工单号：{ticket_no}）"
    return HANDOFF_BASE


def build_warm_handoff_context(state: AgentState, reason: str) -> str:
    """打包转人工上下文：最近若干条消息 + 失败原因 + 已尝试 Agent。"""
    lines = []
    for m in state.get("messages", [])[-8:]:
        if isinstance(m, tuple):
            role, content = m[0], m[1]
        elif hasattr(m, "content"):
            role = getattr(m, "type", "msg")
            content = m.content
        else:
            role, content = "msg", str(m)
        lines.append(f"{role}: {content}")
    payload = {
        "reason": reason,
        "attempted_agent": state.get("next_agent", ""),
        "transcript": "\n".join(lines),
    }
    return json.dumps(payload, ensure_ascii=False)


async def push_to_chatwoot(user_id: str, session_id: str, reason: str, context_summary: str) -> bool:
    """把转人工会话推送到 Chatwoot（未配置则静默跳过，退化为仅落库）。"""
    try:
        return await get_chatwoot_client().push_escalation(user_id, session_id, reason, context_summary)
    except Exception as e:
        logger.warning("推送 Chatwoot 异常: %s", e)
        return False


class HumanHandoffNode:
    """LangGraph 节点：转人工（主动请求 or 熔断升级汇聚到此）。"""

    async def __call__(self, state: AgentState) -> dict:
        user_id = state.get("user_id", "unknown")
        session_id = state.get("session_id", "unknown")
        reason = state.get("handoff_reason") or "用户主动请求转人工"
        context_summary = build_warm_handoff_context(state, reason)
        ticket_no = create_ticket(user_id, session_id, reason, context_summary)
        await push_to_chatwoot(user_id, session_id, reason, context_summary)
        logger.info("转人工: user=%s session=%s reason=%s ticket=%s", user_id, session_id, reason, ticket_no)
        return {"messages": [AIMessage(content=handoff_message(ticket_no))], "escalate_to_human": True}

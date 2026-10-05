"""
文件职能: 寒暄/闲聊 Agent（concierge）—— 应对问候、感谢、无实质内容的对话。
不挂 RAG 工具、不参与反幻觉门（避免「好的/谢谢」被误升级转人工）。
"""
from typing import Dict, Any

from langchain_core.messages import AIMessage

from core.workflow.state import AgentState
from core.resilience.llm import get_llm

_SYSTEM_PROMPT = (
    "你是数码电商「数码优选」的智能客服。用户发来寒暄、感谢或无实质内容的消息。"
    "请友好、简短地回应（1-2 句），并自然地引导用户说出具体需求（商品参数、订单物流、优惠、推荐、比价、售后等）。"
    "不要编造商品信息，不要回答具体商品问题。"
)


class ConciergeAgentNode:
    """寒暄 Agent：问候/感谢/闲聊 → 友好回应 + 引导需求。"""

    def __init__(self):
        self.llm = get_llm(temperature=0.3)

    @staticmethod
    def _extract_text(messages) -> str:
        last = messages[-1]
        if isinstance(last, tuple):
            return last[1]
        if hasattr(last, "content"):
            return last.content
        return str(last)

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        text = self._extract_text(state.get("messages", []))
        resp = await self.llm.ainvoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
        return {"messages": [AIMessage(content=resp.content.strip())]}

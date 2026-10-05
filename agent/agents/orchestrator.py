"""
文件职能：总路由 —— 分析用户意图，决定分发给哪个子 Agent（含「转人工」）。
"""
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.workflow.state import AgentState
from core.resilience.llm import get_llm
from core.policy import detect_rule_escalation

# 寒暄/闲聊词（短消息 + 命中 → concierge，避免「好的/谢谢」被误转人工）
GREETING_KEYWORDS = [
    "你好", "您好", "早上好", "晚上好", "在吗", "在不在", "在么",
    "谢谢", "感谢", "好的", "嗯", "哦", "拜拜", "再见", "hello", "hi",
    "ok", "明白", "知道了", "好的谢谢", "谢谢啦", "麻烦了",
]


class OrchestratorAgent:
    """总路由：分析用户意图，决定分发给哪个子 Agent"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)

    @staticmethod
    def _extract_text(messages) -> str:
        last = messages[-1]
        if isinstance(last, tuple):
            return last[1]
        if hasattr(last, "content"):
            return last.content
        return str(last)

    async def route(self, state: AgentState) -> Dict[str, Any]:
        last_message = self._extract_text(state.get("messages", []))
        query_lower = last_message.lower()

        # ① 转人工/欺诈/法律优先（确定性规则，在 LLM 之前命中）
        rule = detect_rule_escalation(last_message)
        if rule is not None:
            _trigger, reason = rule
            return {"next_agent": "human_handoff", "handoff_reason": reason}

        # ①.5 寒暄/闲聊（短消息 + 寒暄词）→ concierge
        if len(last_message.strip()) <= 6 and any(k in query_lower for k in GREETING_KEYWORDS):
            return {"next_agent": "concierge", "handoff_reason": ""}

        # ② 关键词兜底路由（高置信度关键词直接路由，避免 LLM 判断不稳定）
        # 商品 Agent 统一承接：参数咨询 / 推荐 / 比价 / 关系查询
        if any(k in query_lower for k in [
            "区别", "对比", "哪个好", "哪个划算", "哪个值得", "比较",
            "推荐", "买什么", "预算", "选什么",
            "有哪些", "什么品牌", "哪些型号", "哪些系列", "什么系列",
        ]):
            next_node = "product_agent"
        elif any(k in query_lower for k in ["优惠", "券", "满减", "折扣", "活动", "促销"]):
            next_node = "promotion_agent"
        elif any(k in query_lower for k in ["物流", "订单", "买了什么", "发货", "到哪"]):
            next_node = "order_agent"
        elif any(k in query_lower for k in ["退货", "换货", "保修", "维修", "售后"]):
            next_node = "after_sales_agent"
        else:
            # ③ LLM 路由（处理关键词没覆盖的模糊情况）
            next_node = await self._llm_route(state, last_message)

        return {"next_agent": next_node, "handoff_reason": ""}

    async def _llm_route(self, state: AgentState, last_message: str) -> str:
        system_prompt = f"""你是数码电商智能客服的总路由。
你的任务是根据用户提问，决定分发给哪个专业 Agent。
可用子 Agent：
1. product_agent：商品参数咨询、商品推荐、比价对比
2. order_agent：订单、物流查询
3. promotion_agent：优惠券、促销活动
4. after_sales_agent：退换货、售后维修
5. human_handoff：用户明确要求转人工、或情绪激动强烈要求人工处理

【用户背景记忆】：
{state.get("memory_context", "")}

请只输出要路由到的名称（上面 5 个之一），不要输出其他文字。
无法判断时默认 product_agent。"""

        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=last_message),
        ])
        decision = response.content.strip().lower()

        if "order" in decision:
            return "order_agent"
        if "promotion" in decision:
            return "promotion_agent"
        if "after_sales" in decision:
            return "after_sales_agent"
        if "human" in decision or "人工" in decision:
            return "human_handoff"
        return "product_agent"  # 默认兜底

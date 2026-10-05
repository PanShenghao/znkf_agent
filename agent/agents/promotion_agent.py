"""
文件职能: 优惠活动 Agent —— 查优惠券、促销活动。
"""
from typing import Dict, Any

from langgraph.prebuilt import create_react_agent

from core.workflow.state import AgentState
from core.resilience.llm import get_llm
from core.mcp.loader import get_mcp_tools
from core.streaming import run_react_agent


class PromotionAgentNode:
    """优惠活动 Agent：查询优惠券和促销活动"""

    def __init__(self):
        self.llm = get_llm(temperature=0.3)  # 营销话术需要一点创造性

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        config = {"configurable": {"user_id": state.get("user_id", "unknown")}}
        memory_context = state.get("memory_context", "")

        by_name = await get_mcp_tools()
        tools = [by_name[n] for n in {"get_coupons", "search_product_catalog"} if n in by_name]

        system_prompt = f"""你是数码电商的优惠活动 Agent。
你的任务是帮用户了解当前的优惠券、满减、促销活动。
工作要求：
- 查优惠券用 get_coupons 工具
- 查具体商品活动用 search_product_catalog 工具
- 语气热情，介绍清楚优惠力度和使用条件

【用户背景记忆】：
{memory_context if memory_context else "暂无背景"}"""

        inner_agent = create_react_agent(model=self.llm, tools=tools, prompt=system_prompt)
        final_msg = await run_react_agent(inner_agent, {"messages": state["messages"]}, config=config)
        return {"messages": [final_msg]}

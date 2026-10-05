"""
文件职能: 售后/维修 Agent —— 退换货、保修、维修流程。
"""
from typing import Dict, Any

from langgraph.prebuilt import create_react_agent

from core.workflow.state import AgentState
from core.resilience.llm import get_llm
from core.mcp.loader import get_mcp_tools
from core.streaming import run_react_agent


class AfterSalesAgentNode:
    """售后/维修 Agent：处理退换货、保修、维修咨询"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)  # 售后流程要严谨

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        config = {"configurable": {"user_id": state.get("user_id", "unknown")}}
        memory_context = state.get("memory_context", "")

        by_name = await get_mcp_tools()
        tools = [by_name[n] for n in {"query_after_sales", "query_user_orders"} if n in by_name]

        system_prompt = f"""你是数码电商的售后/维修 Agent。
你的任务是帮用户处理退换货、保修、维修等售后问题。
工作要求：
- 查售后单用 query_after_sales 工具
- 查订单用 query_user_orders 工具（先确认购买信息）
- 系统会自动注入 user_id，只查询当前用户本人的数据
- 流程要清晰专业，安抚用户情绪

【用户背景记忆】：
{memory_context if memory_context else "暂无背景"}"""

        inner_agent = create_react_agent(model=self.llm, tools=tools, prompt=system_prompt)
        final_msg = await run_react_agent(inner_agent, {"messages": state["messages"]}, config=config)
        return {"messages": [final_msg]}

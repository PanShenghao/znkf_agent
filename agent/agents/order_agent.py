"""
文件职能: 订单/物流 Agent —— 查订单、查物流。
安全拦截器 UserIdInjector 已移至 core/mcp/interceptor.py，MCP 工具统一走 core/mcp/loader.py。
"""
from typing import Dict, Any

from langgraph.prebuilt import create_react_agent

from core.workflow.state import AgentState
from core.resilience.llm import get_llm
from core.mcp.loader import get_mcp_tools
from core.streaming import run_react_agent


class OrderAgentNode:
    """订单/物流 Agent：查用户的订单记录和物流进度"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)  # 查订单要严谨

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        config = {"configurable": {"user_id": state.get("user_id", "unknown")}}
        memory_context = state.get("memory_context", "")

        by_name = await get_mcp_tools()
        tools = [by_name[n] for n in {"query_user_orders", "query_logistics"} if n in by_name]

        system_prompt = f"""你是数码电商的订单/物流查询 Agent。
你可以用工具查询用户的订单记录和物流进度。
工作要求：
- 查订单用 query_user_orders，查物流用 query_logistics
- 系统会自动注入 user_id，调用工具时 user_id 传占位符 "auto" 即可
- 永远只查询当前登录用户本人的数据，禁止越权查他人
- 严禁伪造订单号、物流状态

【用户背景记忆】：
{memory_context if memory_context else "暂无背景"}"""

        inner_agent = create_react_agent(model=self.llm, tools=tools, prompt=system_prompt)
        final_msg = await run_react_agent(inner_agent, {"messages": state["messages"]}, config=config)
        return {"messages": [final_msg]}

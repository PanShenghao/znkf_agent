"""
文件职能：商品/导购 Agent —— 统一处理商品参数咨询、推荐、比价三类需求。
靠「向量检索 + 图谱检索 + 商品目录」三个工具查事实，而非模型瞎编。
"""
from typing import Dict, Any

from langgraph.prebuilt import create_react_agent

from core.workflow.state import AgentState
from core.resilience.llm import get_llm
from core.streaming import run_react_agent
from core.context import retrieval_grounding_note
from core.mcp.loader import get_mcp_tools
from tools.vector_tool import query_vector_db
from tools.graph_tool import query_knowledge_graph


class ProductAgentNode:
    """商品/导购 Agent：参数咨询 + 推荐 + 比价"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        config = {"configurable": {"user_id": state.get("user_id", "unknown")}}
        memory_context = state.get("memory_context", "")

        by_name = await get_mcp_tools()
        mcp_tools = [by_name[n] for n in {"search_product_catalog"} if n in by_name]
        tools = [query_vector_db, query_knowledge_graph] + mcp_tools

        system_prompt = f"""你是数码电商的商品/导购 Agent。
{retrieval_grounding_note()}

职责（按用户意图）：
1. 商品参数咨询（内存/屏幕/芯片等）→ 用 query_knowledge_graph / query_vector_db
2. 商品推荐（按预算/需求）→ 用 search_product_catalog + query_vector_db
3. 比价对比 → 用 search_product_catalog + query_vector_db

工具：
1. query_vector_db：查商品文档（概念/教程/政策/规格）
2. query_knowledge_graph：查商品参数、品牌系列关系（精确结构）
3. search_product_catalog：查在售商品列表

工作要求：
- 自主决定用哪个工具，复杂问题可组合使用
- 推荐/比价时，必须以 search_product_catalog 的真实在售商品为准，严禁虚构
- 「有哪些/什么品牌/哪些型号/什么系列」这类关系问题，优先用 query_knowledge_graph
- 若 query_knowledge_graph 返回「未找到」，必须再用 query_vector_db 查文档（图谱只收录部分商品，文档更全）
- 若工具返回「[无检索证据]」或「未找到」，必须如实告知用户「暂无法确认」，严禁编造参数/价格
- 答案结尾列出实际数据来源

【用户背景记忆】：
{memory_context if memory_context else "暂无背景"}
"""

        inner_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            prompt=system_prompt,
        )
        final_msg = await run_react_agent(inner_agent, {"messages": state["messages"]}, config=config)
        return {"messages": [final_msg]}

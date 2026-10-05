"""
文件职能：用 LangGraph 把「路由 + 6 子 Agent + 转人工」组装成一张状态图。
"""
from langgraph.graph import StateGraph, START, END

from core.workflow.state import AgentState
from core.handoff import HumanHandoffNode
from agents.orchestrator import OrchestratorAgent
from agents.product_agent import ProductAgentNode
from agents.order_agent import OrderAgentNode
from agents.promotion_agent import PromotionAgentNode
from agents.after_sales_agent import AfterSalesAgentNode
from agents.concierge_agent import ConciergeAgentNode


class AgentGraphManager:
    """负责组装 LangGraph 多智能体编排"""

    def __init__(self):
        self.orchestrator = OrchestratorAgent()
        self.product_node = ProductAgentNode()
        self.order_node = OrderAgentNode()
        self.promotion_node = PromotionAgentNode()
        self.after_sales_node = AfterSalesAgentNode()
        self.concierge_node = ConciergeAgentNode()
        self.human_handoff_node = HumanHandoffNode()

    def _route_condition(self, state):
        return state.get("next_agent", "product_agent")

    def build_graph(self):
        builder = StateGraph(AgentState)

        builder.add_node("orchestrator", self.orchestrator.route)
        builder.add_node("product_agent", self.product_node)
        builder.add_node("order_agent", self.order_node)
        builder.add_node("promotion_agent", self.promotion_node)
        builder.add_node("after_sales_agent", self.after_sales_node)
        builder.add_node("concierge", self.concierge_node)
        builder.add_node("human_handoff", self.human_handoff_node)

        builder.add_edge(START, "orchestrator")

        builder.add_conditional_edges(
            "orchestrator", self._route_condition,
            {
                "product_agent": "product_agent",
                "order_agent": "order_agent",
                "promotion_agent": "promotion_agent",
                "after_sales_agent": "after_sales_agent",
                "concierge": "concierge",
                "human_handoff": "human_handoff",
            }
        )

        builder.add_edge("product_agent", END)
        builder.add_edge("order_agent", END)
        builder.add_edge("promotion_agent", END)
        builder.add_edge("after_sales_agent", END)
        builder.add_edge("concierge", END)
        builder.add_edge("human_handoff", END)

        return builder.compile()

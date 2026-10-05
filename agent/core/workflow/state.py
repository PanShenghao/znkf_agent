import operator
from typing import Annotated, TypedDict, Any, Sequence
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
       LangGraph 全局状态。
       负责在 Router、各个子 Agent 以及 Memory 之间传递信息。
       """
    # 消息记录，使用 operator.add 将新消息追加到列表末尾
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # 决定下一步走向哪个节点的路由标记
    next_agent: str

    # 用户信息，用于鉴权和记忆隔离
    user_id: str
    session_id: str

    # 注入的记忆信息 (长短期记忆提取出的背景上下文)
    memory_context: str

    # 工具调用的附带信息或元数据
    metadata: dict[str, Any]

    # 是否已转人工（供服务层识别，返回转接话术而非继续兜底）
    escalate_to_human: bool

    # 转人工原因（主动请求 / 熔断 / 连续失败等）
    handoff_reason: str


class AgentOutput(TypedDict):
    """Agent 执行的标准输出格式。"""
    response: str
    tool_calls: list[dict[str, Any]]
    metadata: dict[str, Any]


def make_initial_state(
    user_id: str,
    session_id: str,
    query: str | None = None,
    memory_context: str = "",
) -> AgentState:
    """构造一份完整的初始状态，避免各处手写 dict 时漏字段（LangGraph 要求状态键完整）。"""
    messages: list = [("user", query)] if query else []
    return {
        "messages": messages,
        "user_id": user_id,
        "session_id": session_id,
        "memory_context": memory_context,
        "next_agent": "",
        "metadata": {},
        "escalate_to_human": False,
        "handoff_reason": "",
    }

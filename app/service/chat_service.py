"""核心服务逻辑：语义缓存 → 熔断短路 → 记忆+图（真令牌流式 + 升级转人工）→ 流式返回。

升级决策集中在 core/policy.py（策略对象 + 两条门），工单状态机在 core/tickets.py。
"""
import asyncio
import json
import os
import sys
import uuid

# 把 agent 目录加进 sys.path
AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from config import get_settings
from core.workflow.graph_manager import AgentGraphManager
from core.workflow.state import make_initial_state
from core.memory.memory_manager import MemoryManager
from core.resilience.llm import get_llm, get_llm_breaker
from core.resilience.failure_tracker import FailureTracker
from core.policy import EscalationPolicy, EscalationTrigger, decide_execution_escalation, decide_grounding_escalation
from core.handoff import build_warm_handoff_context, handoff_message, push_to_chatwoot
from core.tickets import create_ticket, ensure_ticket_tables
from core.grounding import reset_evidence, any_found
from core.observability import TokenUsageCallback, reset_usage, aggregate_usage, flush_token_usage
from core.logger import get_logger, set_request_id
from infra.cache import semantic_cache

logger = get_logger(__name__)

graph = None
memory = None
failure_tracker = None

# 使用 RAG 检索（query_vector_db / query_knowledge_graph）的 Agent：无证据时应升级而非编造
RAG_AGENTS = {"product_agent"}


def _warmup_rag():
    """预热 RAG（预建 BM25 + 加载 Milvus），失败静默。"""
    try:
        from tools.vector_tool import warmup
        warmup()
    except Exception:
        pass


async def init_agent_system():
    """启动时初始化图 + 记忆 + 缓存 + 失败计数 + 工单表（全局单例）"""
    global graph, memory, failure_tracker
    if graph is None:
        graph_manager = AgentGraphManager()
        graph = graph_manager.build_graph()
        settings = get_settings()
        memory = MemoryManager(
            redis_url=settings.redis_url,
            milvus_host=settings.milvus_host,
            milvus_port=settings.milvus_port,
            embedding_api_key=settings.dashscope_api_key,
        )
        await memory.initialize()
        await semantic_cache.initialize()
        failure_tracker = FailureTracker(settings.redis_url, settings.human_escalation_threshold)
        await failure_tracker.initialize()
        ensure_ticket_tables()
        # RAG 预热（后台线程：预建 BM25 + 加载 Milvus，避免首个查询冷启动误判）
        asyncio.create_task(asyncio.to_thread(_warmup_rag))
        logger.info("智能体系统初始化完成")


async def _extract_memory_context(user_id, session_id, query):
    """提取记忆上下文（短期历史 + 长期偏好）"""
    parts = []
    if memory and memory.short_term.available:
        history = await memory.short_term.get_messages(user_id, session_id)
        if history:
            parts.append("【近期对话历史】：")
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                parts.append(f"{role}: {msg['content']}")
    if memory and memory.long_term.available:
        prefs = await memory.long_term.retrieve_relevant(user_id, query)
        if prefs:
            parts.append("\n【用户长期偏好】：")
            for p in prefs:
                parts.append(f"- {p}")
    return "\n".join(parts)


async def _save_memory(user_id, session_id, query, response_text):
    """每轮对话后写入短期记忆"""
    if memory and memory.short_term.available:
        await memory.save_conversation(user_id, session_id, [
            {"role": "user", "content": query},
            {"role": "assistant", "content": response_text},
        ])


async def _escalate(user_id, session_id, state, reason):
    """统一转人工出口：建工单 + 推送 Chatwoot + 返回转接话术（带工单号）。"""
    context = build_warm_handoff_context(state, reason)
    ticket_no = create_ticket(user_id, session_id, reason, context)
    await push_to_chatwoot(user_id, session_id, reason, context)
    return handoff_message(ticket_no)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat(query, user_id, session_id):
    """① 语义缓存 → ② 熔断短路 → ③ 记忆+图（真令牌流式）→ ④ 流式返回"""
    set_request_id(uuid.uuid4().hex[:12])
    reset_evidence()  # 每轮清空上轮检索证据
    reset_usage()     # 每轮清空上轮 token 用量
    policy = EscalationPolicy.from_settings()
    breaker = get_llm_breaker()

    yield _sse({"status": "thinking"})

    # ① 语义缓存：L1 精确命中不依赖 LLM/embedding，可安全降级；命中直接返回
    cache_hit = await semantic_cache.get_cache(query, user_id)
    if cache_hit:
        response_text = cache_hit["answer"]
        await _save_memory(user_id, session_id, query, response_text)
        yield _sse({"content": response_text})
        yield _sse({"done": True})
        return

    # ② 熔断短路：LLM 已知不可用，直接转人工（不再打 LLM）
    if not breaker.allow_request():
        decision = decide_execution_escalation(
            breaker_open=True, consecutive_failures=0, response_text=None, policy=policy
        )
        reason = decision.reason if decision else "LLM 服务熔断"
        logger.warning("LLM 熔断已打开，直接转人工: user=%s session=%s", user_id, session_id)
        state = make_initial_state(user_id, session_id, query)
        response_text = await _escalate(user_id, session_id, state, reason)
        await _save_memory(user_id, session_id, query, response_text)
        yield _sse({"content": response_text, "escalated": True})
        yield _sse({"done": True})
        return

    # ③ 记忆 + 图（ainvoke；失败/空回复/无证据升级转人工）
    escalated = False
    response_text = ""
    try:
        mem_context = await _extract_memory_context(user_id, session_id, query)
        state = make_initial_state(user_id, session_id, query, mem_context)
        config = {"configurable": {"user_id": user_id}, "callbacks": [TokenUsageCallback()]}

        # ainvoke：拿到 run_react_agent 重建好的「干净最终回答」（不含工具调用前的推理文字）
        result = await graph.ainvoke(state, config=config)
        final_msg = result["messages"][-1]
        response_text = final_msg.content if hasattr(final_msg, "content") else str(final_msg)
        escalated = bool(result.get("escalate_to_human"))

        # 门控（未升级时）：空/过短回复、RAG 无证据
        if not escalated:
            decision = decide_execution_escalation(
                breaker_open=False, consecutive_failures=0, response_text=response_text, policy=policy
            )
            if decision is None:
                decision = decide_grounding_escalation(
                    is_rag_turn=(result.get("next_agent") or "") in RAG_AGENTS,
                    any_evidence=any_found(),
                )
            if decision is not None:
                logger.warning("升级转人工（%s）: user=%s", decision.trigger.value, user_id)
                state = make_initial_state(user_id, session_id, query)
                response_text = await _escalate(user_id, session_id, state, decision.reason)
                escalated = True

        breaker.record_success()
        if failure_tracker:
            await failure_tracker.reset(user_id, session_id)
        if not escalated and response_text:
            await semantic_cache.set_cache(query, response_text, user_id)
        yield _sse({"content": response_text, "escalated": escalated})
    except Exception as e:
        logger.exception("图执行失败: %s", e)
        breaker.record_failure()
        state = make_initial_state(user_id, session_id, query)
        count = 0
        if failure_tracker:
            count = await failure_tracker.record_failure(user_id, session_id)
        decision = decide_execution_escalation(
            breaker_open=False, consecutive_failures=count, response_text=None, policy=policy
        )
        if decision and decision.trigger == EscalationTrigger.CONSECUTIVE_FAILURES:
            response_text = await _escalate(user_id, session_id, state, decision.reason)
            escalated = True
        else:
            response_text = "系统繁忙，请稍后重试。"
        yield _sse({"content": response_text, "escalated": escalated})

    # token 用量落库（后台异步，不阻塞响应）
    agg = aggregate_usage()
    if agg:
        asyncio.create_task(asyncio.to_thread(flush_token_usage, user_id, session_id, agg))

    await _save_memory(user_id, session_id, query, response_text)
    yield _sse({"done": True, "escalated": escalated})


async def end_session(user_id, session_id):
    """会话结束：从短期对话提炼长期偏好（此前该能力在 HTTP 流程里一直是死代码）。"""
    if memory is None:
        return
    llm = get_llm(temperature=0)
    await memory.finalize_session(user_id, session_id, llm)
    logger.info("会话结束，已提炼长期偏好: user=%s session=%s", user_id, session_id)


async def get_session_history(user_id, session_id):
    """返回会话历史消息（从 Redis 短期记忆），供前端恢复会话（跨设备/刷新）。"""
    if memory is None or not memory.short_term.available:
        return []
    return await memory.short_term.get_messages(user_id, session_id)

"""
文件职能: CLI 入口 —— 初始化记忆 + 组装图，提供交互式/单次问答。
"""
import time
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# 把 agent 目录加进 sys.path，这样 import config/core/agents 才能找到
sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from core.resilience.llm import get_llm
from core.memory.memory_manager import MemoryManager
from core.workflow.graph_manager import AgentGraphManager
from core.workflow.state import make_initial_state


async def _extract_memory_context(memory, user_id, session_id, query):
    """提取记忆上下文（短期历史 + 长期偏好）"""
    parts = []
    if memory.short_term.available:
        history = await memory.short_term.get_messages(user_id, session_id)
        if history:
            parts.append("【近期对话历史】：")
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                parts.append(f"{role}: {msg['content']}")
    if memory.long_term.available:
        prefs = await memory.long_term.retrieve_relevant(user_id, query)
        if prefs:
            parts.append("\n【用户长期偏好】：")
            for p in prefs:
                parts.append(f"- {p}")
    return "\n".join(parts)


async def main():
    parser = argparse.ArgumentParser(description="数码电商多智能体客服")
    parser.add_argument("--query", "-q", type=str, help="单次问答模式")
    parser.add_argument("--user", "-u", type=str, default="user_1001")
    parser.add_argument("--session", "-s", type=str, default=None)
    args = parser.parse_args()

    settings = get_settings()
    user_id = args.user
    session_id = args.session or f"session_{uuid.uuid4().hex[:8]}"

    # 用于摘要压缩 / 偏好提炼的 LLM（温度 0，总结要稳定）
    llm = get_llm(temperature=0)

    # 初始化记忆系统
    t0 = time.time()
    memory = MemoryManager(
        redis_url=settings.redis_url,
        milvus_host=settings.milvus_host,
        milvus_port=settings.milvus_port,
        embedding_api_key=settings.dashscope_api_key,
    )
    await memory.initialize()
    t1 = time.time()
    print(f"⏱  [计时] 记忆初始化: {t1 - t0:.2f}s")

    # 初始化图（组装路由 + 6 子 Agent + 转人工）
    graph_manager = AgentGraphManager()
    graph = graph_manager.build_graph()
    t2 = time.time()
    print(f"⏱  [计时] 图组装: {t2 - t1:.2f}s")

    try:
        if args.query:
            # 单次问答模式
            mem_context = await _extract_memory_context(memory, user_id, session_id, args.query)
            state = make_initial_state(user_id, session_id, args.query, mem_context)
            t3 = time.time()
            result = await graph.ainvoke(state)
            t4 = time.time()
            print(f"⏱  [计时] 图执行(路由+Agent+工具): {t4 - t3:.2f}s")
            print(f"\n🤖 AI: {result['messages'][-1].content}\n")
        else:
            # 交互模式（循环对话）
            state = make_initial_state(user_id, session_id)
            while True:
                user_input = input("\n👤 你: ").strip()
                if user_input.lower() in ("quit", "exit", "q"):
                    break
                if not user_input:
                    continue
                mem_context = await _extract_memory_context(memory, user_id, session_id, user_input)
                state["messages"].append(("user", user_input))
                state["memory_context"] = mem_context
                result = await graph.ainvoke(state)
                state["messages"] = result["messages"]
                print(f"\n🤖 AI: {result['messages'][-1].content}\n")
                if memory.short_term.available:
                    await memory.save_conversation(user_id, session_id, [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": result["messages"][-1].content},
                    ])
                    # 历史太长时，摘要式压缩（替代简单截断）
                    await memory.compress_history(user_id, session_id, llm)
    finally:
        await memory.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Windows 控制台/管道默认 GBK，统一转 UTF-8，避免子进程捕获输出乱码/报错
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(main())

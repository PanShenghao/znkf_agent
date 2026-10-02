"""
文件职能: 子 Agent 流式执行 helper。
关键点：create_react_agent(...).ainvoke() 内部走模型的 ainvoke（非流式），外层拿不到 token。
要让最终回答逐 token 流出，子 Agent 必须用 inner_agent.astream(stream_mode="messages")。
此函数既让 token 通过回调流到外层（供 astream_events 捕获），又重建最后一个 AIMessage 作为节点返回值。
"""
from langchain_core.messages import AIMessageChunk


async def run_react_agent(inner_agent, input, config=None):
    """流式执行 ReAct agent，返回最终回答消息（AIMessageChunk）。

    - 正常路径：astream(stream_mode="messages") 逐 token 流出，并按 langgraph_step 重建最后一条消息。
    - 兜底路径：流式出错 / 重建结果异常时，回退到 ainvoke 拿正确最终消息。
    """
    try:
        final_msg = None
        current_step = None
        current_msg = None
        async for chunk, meta in inner_agent.astream(input, config=config, stream_mode="messages"):
            if not isinstance(chunk, AIMessageChunk):
                continue
            step = meta.get("langgraph_step")
            if step != current_step:
                # 进入新的 ReAct 迭代：先收好上一条消息，再开始新消息
                if current_msg is not None:
                    final_msg = current_msg
                current_step = step
                current_msg = chunk
            else:
                current_msg = current_msg + chunk if current_msg is not None else chunk
        if current_msg is not None:
            final_msg = current_msg

        # 若结束在「工具调用」而非「最终回答」，说明重建异常，回退
        if final_msg is None or getattr(final_msg, "tool_calls", None):
            raise RuntimeError("stream reconstruction incomplete")

        return final_msg
    except Exception:
        result = await inner_agent.ainvoke(input, config=config)
        return result["messages"][-1]

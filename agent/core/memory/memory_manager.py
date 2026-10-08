"""
文件职能: 把短期、长期、偏好提炼三个组件「组装」起来，提供统一入口。
"""
import asyncio
import logging

from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .preference_extractor import PreferenceExtractor

logger = logging.getLogger(__name__)


class MemoryManager:
    """ 记忆门面：协调短期 + 长期 + 偏好提炼 """
    def __init__(self, redis_url, milvus_host, milvus_port, embedding_api_key):
        # 组装：把配置传给两个组件（依赖注入的最终体现）
        self.short_term = ShortTermMemory(redis_url=redis_url)
        self.long_term = LongTermMemory(host=milvus_host, port=milvus_port, embedding_api_key=embedding_api_key)

    async def initialize(self):
        # 并发初始化两个存储，任一失败不影响另一个
        await asyncio.gather(
            self.short_term.initialize(),
            self.long_term.initialize(),
            return_exceptions=True,   # 异常不抛出，优雅降级
        )

    async def save_conversation(self, user_id, session_id, messages):
        """ 每轮对话后：把本轮对话追加进短期记忆 """
        non_system = [m for m in messages if m.get("role") != "system"]
        existing = await self.short_term.get_messages(user_id, session_id)
        combined = existing + non_system   # 追加不是覆盖
        await self.short_term.save_messages(user_id, session_id, combined)

    async def load_preferences(self, user_id, query, top_k=3):
        """ 新会话开始：从长期记忆检索相关偏好 """
        return await self.long_term.retrieve_relevant(user_id, query, top_k)

    async def finalize_session(self, user_id, session_id, llm):
        """ 会话结束：短期对话 → LLM 提炼 → 存长期 → 清短期 """
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) < 2:
            await self.short_term.clear(user_id, session_id)
            return

        # 把对话拼成文本（只取最近20条）
        conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-20:])
        extractor = PreferenceExtractor(llm=llm)
        existing = await self.load_preferences(user_id, "用户偏好")
        new_items = await extractor.extract(conversation_text, existing)

        for item in new_items:
            await self.long_term.save_memory(user_id, item, "preference")

        await self.short_term.clear(user_id, session_id)

    async def compress_history(self, user_id, session_id, llm):
        """历史太长时，用 LLM 把旧消息总结成摘要（摘要式压缩，替代简单截断）"""
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) <= 20:   # 不够长，不压缩
            return

        recent = messages[-6:]    # 保留最近 6 条
        old = messages[:-6]       # 旧消息要压缩
        old_text = "\n".join(f"{m['role']}: {m['content']}" for m in old)

        prompt = (f"请把以下对话历史总结成一段简洁摘要，保留关键信息"
                  f"（用户需求、偏好、已确认的事实），200字以内：\n\n{old_text}\n\n摘要：")
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        summary = resp.content.strip()

        new_msgs = [{"role": "system", "content": f"【历史对话摘要】{summary}"}] + recent
        await self.short_term.save_messages(user_id, session_id, new_msgs)
        logger.info(f"[MEMORY] 历史压缩完成：{len(old)} 条 → 1 条摘要")

    async def close(self):
        await asyncio.gather(
            self.short_term.close(),
            self.long_term.close(),
            return_exceptions=True,
        )

"""
文件职能: 用 LLM 从一堆对话里「总结」出用户偏好。
"""

import logging

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """分析以下对话，提取用户的偏好、习惯和个人信息。
每条用单独一行，格式为"类别: 内容"。
只包含具体的、可操作的用户信息。
如果没有相关信息，就输出: 无
所有输出内容必须用中文。

提取示例：
  品类偏好: 手机
  品牌偏好: 苹果
  预算: 5000元
  习惯: 喜欢大屏

对话内容：
{conversation}

提取结果（或"无"）："""


class PreferenceExtractor:
    """用 LLM 从对话中提炼用户偏好"""

    def __init__(self, llm, max_conversation_chars=3000):
        self.llm = llm
        self.max_conversation_chars = max_conversation_chars

    async def extract(self, conversation_text, existing=None):
        # 截断，控制 token 消耗
        truncated = conversation_text[:self.max_conversation_chars]
        prompt = _PROMPT_TEMPLATE.format(conversation=truncated)

        # 让 LLM 提炼
        response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
        raw = response.content.strip()

        # 没提炼到就返回空列表
        if not raw or raw in ("无", "NONE", "无相关信息"):
            return []

        # 解析"类别: 内容"格式
        candidates = [line.strip() for line in raw.split("\n") if ":" in line]
        if not candidates:
            return []

        # 去重：跳过和已有偏好重复的
        if not existing:
            return candidates
        existing_lower = [e.lower() for e in existing]
        new_items = []
        for item in candidates:
            if any(item.lower() in ex or ex in item.lower() for ex in existing_lower):
                continue
            new_items.append(item)
        return new_items

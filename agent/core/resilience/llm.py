"""
文件职能: 统一 LLM 客户端工厂。
所有 Agent / 记忆 / 图谱查询统一从这里拿 ChatOpenAI，统一配置「超时 + 重试」
（langchain-openai 原生支持 timeout / max_retries），并暴露 provider 级熔断器供上层短路降级。
"""
from langchain_openai import ChatOpenAI

from config import get_settings
from core.resilience.circuit_breaker import get_circuit_breaker

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """返回配置了超时 + 重试的 ChatOpenAI。杜绝各处裸构造 ChatOpenAI。"""
    settings = get_settings()
    return ChatOpenAI(
        api_key=settings.dashscope_api_key,
        model=settings.model,
        base_url=settings.base_url or DEFAULT_BASE_URL,
        temperature=temperature,
        request_timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def get_llm_breaker():
    """LLM provider 熔断器（供上层 chat_service 做短路 / 转人工用）。"""
    settings = get_settings()
    return get_circuit_breaker(
        f"llm:{settings.model}",
        failure_threshold=settings.cb_failure_threshold,
        reset_timeout=settings.cb_reset_timeout,
    )

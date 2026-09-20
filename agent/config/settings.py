from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 自动读取 agent/.env（绝对路径，从任意目录启动都能找到）
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    dashscope_api_key: str = Field(alias="DASHSCOPE_API_KEY")
    model: str = Field(default="qwen-plus", alias="MODEL")
    base_url: str | None = Field(default=None, alias="BASE_URL")

    # ---- 存储 ----
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    # 默认值与 scripts/ingest_graph.py、docker-compose 的 NEO4J_AUTH 保持一致
    neo4j_password: str = Field(default="cloudagent123", alias="NEO4J_PASSWORD")
    mysql_host: str = Field(default="127.0.0.1", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="root", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="digital_shop", alias="MYSQL_DATABASE")

    # ---- 安全（最小鉴权）----
    auth_secret: str = Field(default="", alias="AUTH_SECRET")
    auth_token_ttl: int = Field(default=86400, alias="AUTH_TOKEN_TTL")

    # ---- 熔断 / 重试 ----
    cb_failure_threshold: int = Field(default=3, alias="CB_FAILURE_THRESHOLD")
    cb_reset_timeout: int = Field(default=60, alias="CB_RESET_TIMEOUT")
    llm_timeout: int = Field(default=30, alias="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    human_escalation_threshold: int = Field(default=3, alias="HUMAN_ESCALATION_THRESHOLD")

    # ---- 转人工 → Chatwoot（可选：未配置则退化为仅写 MySQL 队列）----
    chatwoot_url: str = Field(default="", alias="CHATWOOT_URL")
    chatwoot_access_token: str = Field(default="", alias="CHATWOOT_ACCESS_TOKEN")
    chatwoot_account_id: str = Field(default="", alias="CHATWOOT_ACCOUNT_ID")
    chatwoot_api_inbox_id: str = Field(default="", alias="CHATWOOT_API_INBOX_ID")

    # ---- 可观测 / 计费（token 单价快照，单位：元/百万 token，请按最新价覆盖）----
    llm_input_price_per_1m: float = Field(default=0.8, alias="LLM_INPUT_PRICE_PER_1M")
    llm_output_price_per_1m: float = Field(default=2.0, alias="LLM_OUTPUT_PRICE_PER_1M")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("dashscope_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """校验 API key 非空"""
        if not v or v.strip() == "":
            raise ValueError("DASHSCOPE_API_KEY cannot be empty")
        return v.strip()


# 装饰器：缓存结果，避免每次调用都重新读配置
@lru_cache
def get_settings() -> Settings:
    return Settings()

"""
文件职能: 最小鉴权 —— 签发/校验 HMAC 签名 token。
服务端从 token 解出 user_id，不再信任请求体里的 user_id（堵住「伪造 user_id 越权」漏洞）。
"""
import logging

from itsdangerous import URLSafeTimedSerializer

from config import get_settings

logger = logging.getLogger(__name__)

# 未配置 AUTH_SECRET 时的开发兜底（生产/容器必须通过环境变量配置，见 .env.example）
_DEV_SECRET = "znkf-dev-secret-change-me"


def _secret() -> str:
    s = get_settings()
    if not s.auth_secret:
        logger.warning("AUTH_SECRET 未配置，使用开发兜底密钥（仅限本地调试，生产请务必配置）")
        return _DEV_SECRET
    return s.auth_secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret(), salt="znkf-auth")


def issue_token(user_id: str, max_age: int | None = None) -> str:
    """签发 token，返回签名字符串。"""
    s = get_settings()
    return _serializer().dumps({"user_id": user_id})


def verify_token(token: str) -> str:
    """校验 token 并返回 user_id；失败抛 itsdangerous 异常。"""
    s = get_settings()
    data = _serializer().loads(token, max_age=s.auth_token_ttl)
    user_id = data.get("user_id")
    if not user_id:
        raise ValueError("invalid token payload")
    return str(user_id)


def verify_internal_token(token: str) -> bool:
    """校验内部/人工侧调用令牌（值 = AUTH_SECRET）。用于工单状态机等后端间接口。"""
    return bool(token) and token == _secret()

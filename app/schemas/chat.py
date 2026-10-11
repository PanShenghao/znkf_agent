"""请求/响应模型。user_id 不再从请求体取，改由服务端从 token 解出（防伪造越权）。"""
from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default_session"


class TokenRequest(BaseModel):
    user_id: str = "user_1001"


class SessionEndRequest(BaseModel):
    session_id: Optional[str] = "default_session"


class TicketActionRequest(BaseModel):
    ticket_no: str
    operator: Optional[str] = ""

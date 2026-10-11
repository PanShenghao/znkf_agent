"""路由：
- /api/auth/token 发 token
- /api/chat 带 token 鉴权后 SSE 流式
- /api/session/end 结束会话提炼记忆
- /api/tickets/* 工单状态机（人工侧接管/关闭/取消，供 Chatwoot webhook 或坐席工作台调用）
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse

from schemas.chat import ChatRequest, TokenRequest, SessionEndRequest, TicketActionRequest
from service.chat_service import stream_chat, end_session, get_session_history
from security.auth import issue_token, verify_token, verify_internal_token
from core.tickets import takeover_ticket, close_ticket, cancel_ticket

router = APIRouter()


def get_user_id(authorization: str = Header(default="")) -> str:
    """从 Authorization: Bearer <token> 解出 user_id。缺失/无效 → 401。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    try:
        return verify_token(authorization[len("Bearer "):])
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")


def _require_internal(x_internal_token: str = Header(default="")) -> bool:
    """内部/人工侧调用校验（值 = AUTH_SECRET）。"""
    if not verify_internal_token(x_internal_token):
        raise HTTPException(status_code=401, detail="invalid internal token")
    return True


@router.post("/auth/token")
async def auth_token(request: TokenRequest):
    """（dev 友好）用 user_id 换 token。生产可换成真实登录体系。"""
    token = issue_token(request.user_id)
    return {"token": token, "user_id": request.user_id}


@router.post("/chat")
async def chat_endpoint(request: ChatRequest, user_id: str = Depends(get_user_id)):
    return StreamingResponse(
        stream_chat(request.query, user_id, request.session_id),
        media_type="text/event-stream",
    )


@router.post("/session/end")
async def session_end(request: SessionEndRequest, user_id: str = Depends(get_user_id)):
    await end_session(user_id, request.session_id)
    return {"status": "ok"}


@router.get("/session/history")
async def session_history(session_id: str, user_id: str = Depends(get_user_id)):
    messages = await get_session_history(user_id, session_id)
    return {"messages": messages}


@router.post("/tickets/takeover")
def ticket_takeover(request: TicketActionRequest, _: bool = Depends(_require_internal)):
    """坐席接管：待处理 → 接管中。"""
    if not takeover_ticket(request.ticket_no, request.operator or "human"):
        raise HTTPException(status_code=404, detail="工单不存在或状态不允许接管")
    return {"status": "ok"}


@router.post("/tickets/close")
def ticket_close(request: TicketActionRequest, _: bool = Depends(_require_internal)):
    """关闭工单：接管中 → 已关闭（处理完回流 AI）。"""
    if not close_ticket(request.ticket_no, request.operator or "human"):
        raise HTTPException(status_code=404, detail="工单不存在或状态不允许关闭")
    return {"status": "ok"}


@router.post("/tickets/cancel")
def ticket_cancel(request: TicketActionRequest, _: bool = Depends(_require_internal)):
    """取消转接：待处理 → 已取消。"""
    if not cancel_ticket(request.ticket_no, request.operator or "human"):
        raise HTTPException(status_code=404, detail="工单不存在或状态不允许取消")
    return {"status": "ok"}

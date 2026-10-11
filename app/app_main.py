"""
FastAPI 入口：接收 HTTP 请求，调用智能体核心，SSE 流式返回。
附带 /healthz 存活探针与 /readyz 就绪探针（供 docker-compose / 编排系统使用）。
"""
import sys
import os

# 把 agent 目录加进 sys.path（这样能 import config/core/agents）
AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent")
sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import get_settings
from core.logger import setup_logging
from router import chat
from service.chat_service import init_agent_system


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    setup_logging(settings.log_level)
    # 启动时初始化图 + 记忆 + 缓存 + 失败计数
    await init_agent_system()
    yield


app = FastAPI(title="数码电商智能客服 API", lifespan=lifespan)

# CORS：收紧为白名单（不再 allow_origins=["*"] + allow_credentials=True 的矛盾配置）。
# 容器化后前端经 nginx 同源代理，浏览器无需跨域；此白名单仅覆盖本地 vite 开发。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(chat.router, prefix="/api")


@app.get("/healthz")
async def healthz():
    """存活探针：进程活着即返回 OK。"""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """就绪探针：核心依赖（图/记忆/缓存/失败计数）就绪才返回 OK。"""
    from service import chat_service
    ready = chat_service.graph is not None
    return {"status": "ready" if ready else "not_ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_main:app", host="0.0.0.0", port=5000)

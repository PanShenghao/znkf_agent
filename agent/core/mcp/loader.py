"""
文件职能: 共享 MCP 工具加载器（单例）。
所有 MCP Agent 共享同一个 client（1 个 stdio 子进程），避免每个 Agent 各自 spawn 子进程。
原来的 5 份重复配置解析代码收敛到这里。
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from core.mcp.interceptor import UserIdInjector
from config import get_settings

_AGENT_DIR = Path(__file__).resolve().parent.parent.parent  # .../agent
_CONFIG_PATH = _AGENT_DIR / "config" / "mcp_servers.json"

_lock = asyncio.Lock()
_tools_by_name: dict | None = None


def _resolve_servers_config() -> dict:
    """读 mcp_servers.json 并把 cwd/command 解析成绝对路径与当前解释器（部署兼容）。
    并显式把 DB 配置作为 env 传给 MCP 子进程——MCP stdio 客户端只传白名单 env，不会继承自定义变量。"""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    servers = cfg.get("mcpServers", {})
    s = get_settings()
    db_env = {
        "MYSQL_HOST": s.mysql_host,
        "MYSQL_PORT": str(s.mysql_port),
        "MYSQL_USER": s.mysql_user,
        "MYSQL_PASSWORD": s.mysql_password,
        "MYSQL_DATABASE": s.mysql_database,
    }
    for srv in servers.values():
        if srv.get("cwd") and not os.path.isabs(srv["cwd"]):
            srv["cwd"] = os.path.abspath(os.path.join(_AGENT_DIR.parent, srv["cwd"]))
        if srv.get("command") == "python":
            srv["command"] = sys.executable
        # 显式传 DB 环境变量（覆盖/补充已有 env）
        srv["env"] = {**db_env, **(srv.get("env") or {})}
    return servers


async def get_mcp_tools() -> dict:
    """懒加载单例：第一次调用连接 MCP（1 个子进程），之后所有 Agent 复用。"""
    global _tools_by_name
    if _tools_by_name is not None:
        return _tools_by_name
    async with _lock:
        if _tools_by_name is not None:
            return _tools_by_name
        servers = _resolve_servers_config()
        client = MultiServerMCPClient(connections=servers, tool_interceptors=[UserIdInjector()])
        all_tools = await client.get_tools()
        _tools_by_name = {t.name: t for t in all_tools}
        return _tools_by_name

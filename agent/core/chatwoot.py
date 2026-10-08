"""
文件职能: Chatwoot 客户端 —— 把「转人工」的会话推送到 Chatwoot 的 API channel，让真人坐席在工作台接单。
未配置 CHATWOOT_* 时 is_configured() 为 False，调用方退化为仅写 MySQL 队列（不报错、不影响主流程）。
"""
import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


class ChatwootClient:
    def __init__(self, url: str, access_token: str, account_id: str, api_inbox_id: str):
        self.url = (url or "").rstrip("/")
        self.access_token = access_token
        self.account_id = account_id
        self.api_inbox_id = api_inbox_id

    @classmethod
    def from_settings(cls) -> "ChatwootClient":
        s = get_settings()
        return cls(s.chatwoot_url, s.chatwoot_access_token, s.chatwoot_account_id, s.chatwoot_api_inbox_id)

    def is_configured(self) -> bool:
        return bool(self.url and self.access_token and self.account_id and self.api_inbox_id)

    def _headers(self) -> dict:
        return {"api_access_token": self.access_token, "Content-Type": "application/json"}

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self.url}{path}", headers=self._headers(), json=payload)
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _unwrap(data: dict, key: str):
        # 兼容 Chatwoot 两种返回结构：顶层直给 / {"payload": {...}}
        if key in data:
            return data[key]
        return (data.get("payload") or {}).get(key)

    async def _find_or_create_contact(self, identifier: str, name: str) -> dict:
        """按 identifier 找/建 contact（同 identifier 幂等），返回 {contact_id, source_id}。"""
        data = await self._post(
            f"/api/v1/accounts/{self.account_id}/contacts",
            {"inbox_id": self.api_inbox_id, "identifier": identifier, "name": name},
        )
        contact_id = self._unwrap(data, "id")
        contact_inboxes = self._unwrap(data, "contact_inboxes") or []
        source_id = None
        for ci in contact_inboxes:
            if str(ci.get("inbox_id")) == str(self.api_inbox_id):
                source_id = ci.get("source_id")
        if source_id is None:
            source_id = identifier  # 兜底：用 identifier 作 source_id
        return {"contact_id": contact_id, "source_id": source_id}

    async def push_escalation(self, user_id: str, session_id: str, reason: str, context_summary: str) -> bool:
        """转人工时推送到 Chatwoot：建 contact → 建 conversation → 发消息（含 warm handoff 上下文）。"""
        if not self.is_configured():
            return False
        try:
            c = await self._find_or_create_contact(f"znkf-{user_id}", user_id)
            data = await self._post(
                f"/api/v1/accounts/{self.account_id}/conversations",
                {
                    "source_id": c["source_id"],
                    "inbox_id": self.api_inbox_id,
                    "contact_id": c["contact_id"],
                    "status": "open",
                    "custom_attributes": {"reason": reason, "session_id": session_id},
                },
            )
            conv_id = self._unwrap(data, "id")
            if not conv_id:
                logger.warning("Chatwoot 建会话失败：返回无 conversation id")
                return False

            content = f"[转人工] 原因：{reason}\n会话：{session_id}\n\n{context_summary}"
            await self._post(
                f"/api/v1/accounts/{self.account_id}/conversations/{conv_id}/messages",
                {"content": content, "content_type": "text"},
            )
            logger.info("已推送到 Chatwoot: user=%s conversation=%s", user_id, conv_id)
            return True
        except Exception as e:
            logger.warning("推送到 Chatwoot 失败（退化为仅落库）: %s", e)
            return False


_chatwoot_client = None


def get_chatwoot_client() -> ChatwootClient:
    global _chatwoot_client
    if _chatwoot_client is None:
        _chatwoot_client = ChatwootClient.from_settings()
    return _chatwoot_client

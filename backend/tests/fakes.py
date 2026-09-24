"""A fake Telegram Bot API that records every call. Nothing leaves the test."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.telegram.client import TelegramError


@dataclass
class FakeBot:
    token: str
    bot_id: int
    username: str
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    webhook_secret: str | None = None
    fail_with: TelegramError | None = None

    async def call(self, method: str, **params: Any) -> Any:
        if self.fail_with is not None and method != "getMe":
            raise self.fail_with
        self.calls.append((method, params))
        if method == "getMe":
            return {"id": self.bot_id, "is_bot": True, "username": self.username}
        if method == "setWebhook":
            self.webhook_secret = params["secret_token"]
            return True
        if method == "sendMessage":
            return {"message_id": len(self.calls), "chat": {"id": params["chat_id"]}, "text": params["text"]}
        if method == "getChatMember":
            return {"status": self.owner.members.get((params["chat_id"], params["user_id"]), "left")}
        if method == "createChatInviteLink":
            return {"invite_link": f"https://t.me/+fake{params['chat_id']}", "creates_join_request": True}
        return True

    owner: FakeTelegram = field(default=None, repr=False)  # type: ignore[assignment]

    def sent_texts(self, chat_id: int | None = None) -> list[str]:
        return [p["text"] for m, p in self.calls if m == "sendMessage" and (chat_id is None or p["chat_id"] == chat_id)]

    def last_markup(self, chat_id: int) -> dict | None:
        for method, params in reversed(self.calls):
            if method == "sendMessage" and params["chat_id"] == chat_id:
                return params.get("reply_markup")
        return None


class FakeTelegram:
    def __init__(self) -> None:
        self.bots: dict[str, FakeBot] = {}
        self.members: dict[tuple[int, int], str] = {}
        self._next_id = 7_000_000_000

    def api(self, token: str) -> FakeBot:
        if token not in self.bots:
            self._next_id += 1
            name = token.split(":")[0]
            self.bots[token] = FakeBot(token=token, bot_id=self._next_id, username=f"{name}_bot", owner=self)
        return self.bots[token]

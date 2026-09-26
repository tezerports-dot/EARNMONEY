"""A stand-in for Telegram's Bot API, for end-to-end tests.

The server talks to it exactly as it would to api.telegram.org (point
FF_TELEGRAM_API_BASE here). Tests act as a Telegram user through the
/control endpoints, which deliver updates to the bots' webhooks the way
Telegram does: with the webhook secret header, and only the update types each
bot asked for in setWebhook.
"""

from __future__ import annotations

import hashlib
import itertools
from typing import Any

import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="fake Telegram Bot API")

bots: dict[str, dict[str, Any]] = {}  # token -> bot
members: dict[tuple[int, int], str] = {}  # (chat_id, user_id) -> status
sent: list[dict[str, Any]] = []
_update_ids = itertools.count(1)
_message_ids = itertools.count(1)


def _bot_for_token(token: str) -> dict[str, Any]:
    if token not in bots:
        name = token.split(":", 1)[0]
        bot_id = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
        bots[token] = {"id": bot_id, "username": f"{name}_bot", "webhook": None, "secret": None, "allowed": []}
    return bots[token]


def _bot_for_username(username: str) -> dict[str, Any]:
    for bot in bots.values():
        if bot["username"] == username:
            return bot
    raise KeyError(username)


@app.post("/bot{token}/{method}")
async def bot_api(token: str, method: str, request: Request) -> dict[str, Any]:
    params: dict[str, Any] = await request.json() if await request.body() else {}
    bot = _bot_for_token(token)
    if method == "getMe":
        return {"ok": True, "result": {"id": bot["id"], "is_bot": True, "username": bot["username"]}}
    if method == "setWebhook":
        bot.update(webhook=params["url"], secret=params.get("secret_token"), allowed=params.get("allowed_updates", []))
        return {"ok": True, "result": True}
    if method == "sendMessage":
        message = {"message_id": next(_message_ids), "chat": {"id": params["chat_id"]}, "text": params["text"]}
        sent.append({"bot": bot["username"], **params})
        return {"ok": True, "result": message}
    if method == "answerCallbackQuery":
        return {"ok": True, "result": True}
    if method == "getChatMember":
        status = members.get((int(params["chat_id"]), int(params["user_id"])), "left")
        return {"ok": True, "result": {"status": status, "user": {"id": params["user_id"], "is_bot": False}}}
    if method == "createChatInviteLink":
        link = f"https://t.me/+e2e{abs(int(params['chat_id']))}"
        return {"ok": True, "result": {"invite_link": link, "creates_join_request": True}}
    return {"ok": False, "error_code": 400, "description": f"fake Telegram doesn't know {method}"}


async def _deliver(bot: dict[str, Any], update: dict[str, Any]) -> int:
    kind = next(k for k in update if k != "update_id")
    if bot["allowed"] and kind not in bot["allowed"]:
        return 204  # Telegram wouldn't send it to this bot
    async with httpx.AsyncClient() as client:
        response = await client.post(
            bot["webhook"],
            json={"update_id": next(_update_ids), **update},
            headers={"X-Telegram-Bot-Api-Secret-Token": bot["secret"] or ""},
            timeout=10,
        )
    return response.status_code


def _user(user_id: int) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "E2E"}


def _message(user_id: int, **fields: Any) -> dict[str, Any]:
    chat = {"id": user_id, "type": "private"}
    return {"message": {"message_id": next(_message_ids), "from": _user(user_id), "chat": chat, "date": 0, **fields}}


@app.post("/control/start")
async def control_start(body: dict[str, Any]) -> dict[str, int]:
    bot = _bot_for_username(body["bot"])
    return {"status": await _deliver(bot, _message(body["user_id"], text=f"/start {body['token']}"))}


@app.post("/control/join-request")
async def control_join_request(body: dict[str, Any]) -> dict[str, list[int]]:
    """The user taps JOIN on a channel: every bot watching join requests hears it."""
    update = {
        "chat_join_request": {
            "chat": {"id": body["chat_id"], "type": "channel"},
            "from": _user(body["user_id"]),
            "date": 1790000000,
        }
    }
    statuses = [await _deliver(bot, update) for bot in bots.values() if "chat_join_request" in bot["allowed"]]
    return {"statuses": statuses}


@app.post("/control/callback")
async def control_callback(body: dict[str, Any]) -> dict[str, int]:
    bot = _bot_for_username(body["bot"])
    update = {"callback_query": {"id": f"cb{next(_message_ids)}", "from": _user(body["user_id"]), "data": body["data"]}}
    return {"status": await _deliver(bot, update)}


@app.post("/control/contact")
async def control_contact(body: dict[str, Any]) -> dict[str, int]:
    """The user shares their own Telegram number with the bot."""
    bot = _bot_for_username(body["bot"])
    contact = {"phone_number": body["phone"], "first_name": "E2E", "user_id": body["user_id"]}
    return {"status": await _deliver(bot, _message(body["user_id"], contact=contact))}


@app.get("/control/messages")
async def control_messages(user_id: int) -> list[dict[str, Any]]:
    return [m for m in sent if int(m["chat_id"]) == user_id]


@app.get("/control/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "bots": [b["username"] for b in bots.values()]}

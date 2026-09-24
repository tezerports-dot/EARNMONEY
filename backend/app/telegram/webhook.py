"""Telegram webhook endpoint, one URL per bot."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import TelegramBot
from app.redis_client import redis
from app.security.tokens import same, token_hash
from app.services import bots
from app.telegram import flow
from app.telegram.client import TelegramError

log = logging.getLogger("telegram")
router = APIRouter()

DEDUPE_SECONDS = 3600


@router.post("/telegram/webhook/{bot_ref}", include_in_schema=False)
async def webhook(bot_ref: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    async with db.begin():
        bot = (await db.execute(select(TelegramBot).where(TelegramBot.ref == bot_ref[:32]))).scalar_one_or_none()
        # One generic answer for unknown bots and wrong secrets.
        if bot is None or not secret or not same(token_hash(secret), bot.webhook_secret_hash):
            return Response(status_code=401)
        if not bot.enabled:
            return Response(status_code=200)
        bot_id, role = bot.id, bot.role

    try:
        update = await request.json()
    except ValueError:
        return Response(status_code=200)
    update_id = update.get("update_id") if isinstance(update, dict) else None
    if not isinstance(update_id, int):
        return Response(status_code=200)
    dedupe_key = f"tg:upd:{bot_id}:{update_id}"
    if await redis().exists(dedupe_key):
        return Response(status_code=200)

    try:
        async with db.begin():
            bot = await db.get(TelegramBot, bot_id)
            assert bot is not None
            handler = flow.handle_watcher if role == "WATCHER" else flow.handle_verifier
            outgoing = await handler(db, bot, update)
    except Exception:
        # Answering 200 stops Telegram retrying an update that can never work.
        log.exception("telegram update failed", extra={"bot_id": bot_id, "update_id": update_id})
        return Response(status_code=200)
    await redis().set(dedupe_key, "1", ex=DEDUPE_SECONDS)

    if outgoing:
        async with db.begin():
            bot = await db.get(TelegramBot, bot_id)
            assert bot is not None
            for message in outgoing:
                try:
                    await bots.call(bot, message.method, **message.params)
                except TelegramError:
                    log.warning("telegram send failed", extra={"bot_id": bot_id, "method": message.method})
    return Response(status_code=200)

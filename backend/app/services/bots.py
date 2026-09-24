"""The Telegram bot pool: choosing a verifier, tracking health, secrets."""

from __future__ import annotations

import random
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.config import get_settings
from app.models import TelegramBot
from app.security import crypto
from app.security.tokens import token_hash
from app.telegram.client import BotApi, TelegramError, api_for

FAILING_AFTER = 3


def bot_token(bot: TelegramBot) -> str:
    return crypto.decrypt(bot.token_ciphertext, f"bot:{bot.telegram_bot_id}")


def api(bot: TelegramBot) -> BotApi:
    return api_for(bot_token(bot))


async def pick_verifier(db: AsyncSession) -> TelegramBot | None:
    at = timeutil.now()
    bots = list(
        (
            await db.execute(
                select(TelegramBot).where(
                    TelegramBot.role == "VERIFIER",
                    TelegramBot.enabled,
                    or_(
                        TelegramBot.health == "HEALTHY",
                        (TelegramBot.health == "RATE_LIMITED") & (TelegramBot.rate_limited_until <= at),
                    ),
                )
            )
        ).scalars()
    )
    if not bots:
        return None
    return random.choices(bots, weights=[b.weight for b in bots], k=1)[0]


async def can_serve(db: AsyncSession, bot_id: int) -> bool:
    """Whether an open session's bot can still talk to its user. A rate limit
    passes in seconds, so only a failing or switched-off bot counts as gone."""
    bot = await db.get(TelegramBot, bot_id)
    return bot is not None and bot.enabled and bot.health != "FAILING"


async def watcher(db: AsyncSession) -> TelegramBot | None:
    return (
        await db.execute(
            select(TelegramBot)
            .where(TelegramBot.role == "WATCHER", TelegramBot.enabled, TelegramBot.health != "FAILING")
            .order_by(TelegramBot.id)
            .limit(1)
        )
    ).scalar_one_or_none()


def mark_ok(bot: TelegramBot) -> None:
    bot.health = "HEALTHY"
    bot.consecutive_failures = 0
    bot.rate_limited_until = None
    bot.last_ok_at = timeutil.now()


def mark_error(bot: TelegramBot, exc: TelegramError) -> None:
    at = timeutil.now()
    bot.last_error_at = at
    bot.last_error = str(exc)[:200]
    if exc.code == 429:
        bot.health = "RATE_LIMITED"
        bot.rate_limited_until = at + timedelta(seconds=exc.retry_after or 30)
        return
    bot.consecutive_failures += 1
    if bot.consecutive_failures >= FAILING_AFTER:
        bot.health = "FAILING"


async def call(bot: TelegramBot, method: str, **params: Any) -> Any:
    """Call the Bot API and record the bot's health. Raises ``TelegramError``."""
    try:
        result = await api(bot).call(method, **params)
    except TelegramError as exc:
        mark_error(bot, exc)
        raise
    if bot.health != "HEALTHY" or bot.consecutive_failures:
        mark_ok(bot)
    return result


def webhook_url(bot: TelegramBot) -> str:
    return f"{get_settings().public_base_url}/telegram/webhook/{bot.ref}"


async def register(db: AsyncSession, token: str, role: str, weight: int = 1) -> TelegramBot:
    """Add a bot: check the token with getMe, store it encrypted, set the webhook."""
    probe = api_for(token)
    me = await probe.call("getMe")
    secret = secrets.token_urlsafe(32)
    bot = (await db.execute(select(TelegramBot).where(TelegramBot.telegram_bot_id == me["id"]))).scalar_one_or_none()
    if bot is None:
        bot = TelegramBot(ref=secrets.token_urlsafe(12), telegram_bot_id=me["id"])
        db.add(bot)
    bot.role = role
    bot.username = me["username"]
    bot.token_ciphertext = crypto.encrypt(token, f"bot:{me['id']}")
    bot.webhook_secret_hash = token_hash(secret)
    bot.weight = weight
    bot.enabled = True
    bot.health = "HEALTHY"
    bot.consecutive_failures = 0
    await db.flush()
    allowed = ["chat_join_request"] if role == "WATCHER" else ["message", "callback_query"]
    await probe.call(
        "setWebhook",
        url=webhook_url(bot),
        secret_token=secret,
        allowed_updates=allowed,
        drop_pending_updates=False,
        max_connections=40,
    )
    return bot


async def recover(db: AsyncSession) -> int:
    """Probe failing bots and bots whose rate limit has passed."""
    at = timeutil.now()
    bots = (
        await db.execute(
            select(TelegramBot).where(
                TelegramBot.enabled,
                or_(
                    TelegramBot.health == "FAILING",
                    (TelegramBot.health == "RATE_LIMITED") & (TelegramBot.rate_limited_until <= at),
                ),
            )
        )
    ).scalars()
    recovered = 0
    for bot in bots:
        try:
            await call(bot, "getMe")
            recovered += 1
        except TelegramError:
            pass
    return recovered

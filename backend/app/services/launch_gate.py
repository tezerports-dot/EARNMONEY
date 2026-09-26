"""The Telegram Mini App launch gate.

When enabled, the app must send each user back through a Mini App on every open.
Inside it the user's Telegram identity is proved from Telegram's signed initData,
an Adsgram ad is shown, and the server records a short-lived *pass* for that
account. The pass is what the app's data endpoints require (see api.deps.verified),
so a modified app can't skip it, and the pass is only granted when the Telegram
account matches the one the account verified with — nobody passes for another
account, and one Telegram account still maps to exactly one app account.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.config import get_settings
from app.models import AppSettings, TelegramBot, User
from app.redis_client import redis
from app.services import bots
from app.telegram.webapp import InitDataInvalid, validate

NONCE_TTL_SECONDS = 600
INITDATA_MAX_AGE_SECONDS = 3600


def _pass_key(user_id: int) -> str:
    return f"launch:pass:{user_id}"


def _nonce_key(nonce: str) -> str:
    return f"launch:nonce:{nonce}"


async def _watcher_username(db: AsyncSession) -> str | None:
    """The main (watcher) bot the Mini App lives on. Health is ignored: the
    deep link is only a t.me URL, so a temporarily unhealthy bot mustn't lock
    everyone out."""
    return (
        await db.execute(
            select(TelegramBot.username)
            .where(TelegramBot.role == "WATCHER", TelegramBot.enabled)
            .order_by(TelegramBot.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _gate(db: AsyncSession) -> tuple[bool, str | None]:
    """Whether the gate is enabled, and the configured Mini App short name."""
    settings = (await db.execute(select(AppSettings).where(AppSettings.id == 1))).scalar_one()
    return settings.launch_gate_enabled, settings.miniapp_short_name


async def has_pass(user_id: int) -> bool:
    return bool(await redis().exists(_pass_key(user_id)))


async def status(db: AsyncSession, user_id: int) -> dict:
    """What the app asks on launch and on return from the Mini App. When the
    gate isn't actually usable (off, or not configured) it reports passed, so a
    misconfiguration never traps users."""
    enabled, short_name = await _gate(db)
    active = enabled and bool(short_name)
    return {"enabled": active, "passed": (not active) or await has_pass(user_id)}


async def challenge(db: AsyncSession, user: User) -> dict:
    """Start one gate crossing: mint a nonce and return the Mini App deep link."""
    enabled, short_name = await _gate(db)
    if not (enabled and short_name):
        return {"enabled": False, "deep_link": None, "expires_in": 0}
    username = await _watcher_username(db)
    if username is None:
        # Enabled but no watcher bot to host the Mini App: don't trap the user.
        return {"enabled": False, "deep_link": None, "expires_in": 0}
    nonce = secrets.token_urlsafe(24)
    await redis().set(_nonce_key(nonce), str(user.id), ex=NONCE_TTL_SECONDS)
    return {
        "enabled": True,
        "deep_link": f"https://t.me/{username}/{short_name}?startapp={nonce}",
        "expires_in": NONCE_TTL_SECONDS,
    }


async def complete(db: AsyncSession, init_data: str, nonce: str | None) -> dict:
    """Called by the Mini App after its ad. Proves the Telegram identity, checks
    it is this account's own Telegram, and records the pass."""
    watcher = (
        await db.execute(
            select(TelegramBot).where(TelegramBot.role == "WATCHER", TelegramBot.enabled).order_by(TelegramBot.id).limit(1)
        )
    ).scalar_one_or_none()
    if watcher is None:
        raise errors.LaunchGateInvalid()
    try:
        info = validate(init_data, bots.bot_token(watcher), max_age_seconds=INITDATA_MAX_AGE_SECONDS)
    except InitDataInvalid as exc:
        raise errors.LaunchGateInvalid() from exc

    user = (
        await db.execute(select(User).where(User.telegram_user_id == info.telegram_user_id, User.status == "ACTIVE"))
    ).scalar_one_or_none()
    if user is None:
        # This Telegram account isn't the verified Telegram of any active account.
        raise errors.LaunchGateMismatch()

    token = nonce or info.start_param
    if not token:
        raise errors.LaunchGateInvalid()
    owner = await redis().get(_nonce_key(token))
    if owner is None:
        raise errors.LaunchGateInvalid()
    if int(owner) != user.id:
        # The app is signed in as a different account than this Telegram verified.
        raise errors.LaunchGateMismatch()
    await redis().delete(_nonce_key(token))

    settings = (await db.execute(select(AppSettings).where(AppSettings.id == 1))).scalar_one()
    await redis().set(_pass_key(user.id), "1", ex=settings.launch_gate_pass_seconds)
    return {"ok": True}


async def clear_pass(user_id: int) -> None:
    """Used when an account is suspended, so a stale pass can't linger."""
    await redis().delete(_pass_key(user_id))


def public_base_url() -> str:
    return get_settings().public_base_url

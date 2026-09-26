"""Request-level checks shared by the v1 endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, User
from app.security import ratelimit
from app.services import campaign, idempotency, launch_gate, sessions


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            # The last address is the one our own proxy appended.
            return forwarded.split(",")[-1].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _version(raw: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in raw.split("+")[0].split("-")[0].split("."))
    except ValueError:
        return None


@dataclass
class _GateState:
    min_version: str
    download_url: str | None
    maintenance: bool
    message: str | None
    until: str | None
    launch_gate: bool
    loaded_at: float


_gate_cache: _GateState | None = None
GATE_CACHE_SECONDS = 5.0


def reset_gate_cache() -> None:
    global _gate_cache
    _gate_cache = None


async def _gate_state(db: AsyncSession) -> _GateState:
    global _gate_cache
    if _gate_cache is not None and time.monotonic() - _gate_cache.loaded_at < GATE_CACHE_SECONDS:
        return _gate_cache
    async with db.begin():
        settings = await campaign.app_settings(db)
    at = timeutil.now()
    on = settings.maintenance_active and (settings.maintenance_until is None or settings.maintenance_until > at)
    _gate_cache = _GateState(
        min_version=settings.min_app_version,
        download_url=settings.apk_download_url,
        maintenance=on,
        message=settings.maintenance_message if on else None,
        until=timeutil.iso(settings.maintenance_until) if on else None,
        # The gate is only enforceable once a Mini App short name is configured;
        # without it the app has no deep link to send the user to.
        launch_gate=settings.launch_gate_enabled and bool(settings.miniapp_short_name),
        loaded_at=time.monotonic(),
    )
    return _gate_cache


async def app_gate(x_app_version: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> None:
    """Maintenance mode and minimum app version, for every v1 route except /config."""
    state = await _gate_state(db)
    if state.maintenance:
        raise errors.Maintenance(state.message, extra={"until": state.until})
    if x_app_version:
        have, need = _version(x_app_version), _version(state.min_version)
        if have is not None and need is not None and have < need:
            raise errors.UpgradeRequired(extra={"download_url": state.download_url})


@dataclass
class Auth:
    session: AuthSession
    user: User


async def auth(request: Request, db: AsyncSession = Depends(get_db)) -> Auth:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 200:
        raise errors.Unauthenticated()
    async with db.begin():
        session, user = await sessions.authenticate(db, token.strip())
    return Auth(session, user)


async def verified(ctx: Auth = Depends(auth), db: AsyncSession = Depends(get_db)) -> Auth:
    if ctx.user.status == "SUSPENDED":
        raise errors.AccountSuspended()
    if ctx.user.status != "ACTIVE":
        raise errors.AccountNotVerified()
    # The launch gate: an active user's data is only served once they've come
    # back through the Telegram Mini App this session (services.launch_gate).
    state = await _gate_state(db)
    if state.launch_gate and not await launch_gate.has_pass(ctx.user.id):
        raise errors.LaunchGateRequired()
    await ratelimit.hit(ratelimit.USER_READS, ctx.user.id)
    return ctx


def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    return idempotency.validate_key(idempotency_key)

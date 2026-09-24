"""User sessions: short-lived access tokens and rotating refresh tokens."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.config import get_settings
from app.models import AuthSession, User
from app.security.tokens import new_token, token_hash


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    session: AuthSession

    def as_json(self) -> dict:
        return {
            "token_type": "Bearer",
            "access_token": self.access_token,
            "access_expires_at": timeutil.iso(self.session.access_expires_at),
            "refresh_token": self.refresh_token,
            "refresh_expires_at": timeutil.iso(self.session.refresh_expires_at),
        }


async def issue(db: AsyncSession, user: User, user_agent: str | None, family_id: uuid.UUID | None = None) -> IssuedTokens:
    settings = get_settings()
    at = timeutil.now()
    access, refresh = new_token("ffa"), new_token("ffr")
    session = AuthSession(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        access_token_hash=token_hash(access),
        access_expires_at=at + timedelta(minutes=settings.access_token_minutes),
        refresh_token_hash=token_hash(refresh),
        refresh_expires_at=at + timedelta(days=settings.refresh_token_days),
        user_agent=(user_agent or "")[:200] or None,
    )
    db.add(session)
    await db.flush()
    return IssuedTokens(access, refresh, session)


async def authenticate(db: AsyncSession, access_token: str) -> tuple[AuthSession, User]:
    row = (
        await db.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(AuthSession.access_token_hash == token_hash(access_token))
        )
    ).first()
    if row is None:
        raise errors.Unauthenticated()
    session, user = row
    if session.revoked_at is not None or session.access_expires_at <= timeutil.now():
        raise errors.Unauthenticated()
    return session, user


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=timeutil.now())
    )


async def revoke_all_for_user(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=timeutil.now())
    )


async def refresh(db: AsyncSession, refresh_token: str, user_agent: str | None) -> IssuedTokens | None:
    """Rotate: each refresh token works once.

    Reuse means the token leaked, so the whole login (every rotation in the
    family) is revoked. Returns ``None`` in that case; the caller commits the
    revocation and then answers ``SESSION_EXPIRED``.
    """
    at = timeutil.now()
    session = (
        await db.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash(refresh_token)).with_for_update()
        )
    ).scalar_one_or_none()
    if session is None:
        raise errors.SessionExpired()
    if session.rotated_at is not None:
        await revoke_family(db, session.family_id)
        return None
    if session.revoked_at is not None or session.refresh_expires_at <= at:
        raise errors.SessionExpired()
    user = await db.get(User, session.user_id)
    if user is None or user.status == "SUSPENDED":
        await revoke_family(db, session.family_id)
        return None
    session.rotated_at = at
    session.revoked_at = at
    return await issue(db, user, user_agent, family_id=session.family_id)

"""Telegram verification sessions and the moment an account becomes verified."""

from __future__ import annotations

import enum
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.models import (
    MembershipCounter,
    RequiredChannel,
    TelegramBot,
    TelegramVerification,
    TelegramVerificationSession,
    User,
)
from app.models.telegram import OPEN_SESSION_STATUSES
from app.security import crypto, ratelimit
from app.security.tokens import token_hash
from app.services import audit, bots, campaign, referrals, rewards, risk

TOKEN_PREFIX = "vs_"  # noqa: S105 (a prefix, not a secret)


def start_token(session_id: int) -> str:
    return TOKEN_PREFIX + crypto.derived_token(f"vs:{session_id}", 32)


def is_open(session: TelegramVerificationSession) -> bool:
    return session.status in OPEN_SESSION_STATUSES and session.expires_at > timeutil.now()


def public_status(session: TelegramVerificationSession) -> str:
    if session.status in OPEN_SESSION_STATUSES:
        return session.status if session.expires_at > timeutil.now() else "EXPIRED"
    return "EXPIRED" if session.status == "SUPERSEDED" else session.status


async def channel_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(RequiredChannel).where(RequiredChannel.active))).scalar_one()


async def session_json(db: AsyncSession, session: TelegramVerificationSession) -> dict:
    bot = await db.get(TelegramBot, session.bot_id)
    assert bot is not None
    state = public_status(session)
    open_ = state in OPEN_SESSION_STATUSES
    return {
        "status": state,
        "bot_username": bot.username,
        "deep_link": f"https://t.me/{bot.username}?start={start_token(session.id)}" if open_ else None,
        "expires_at": timeutil.iso(session.expires_at),
        "channel_count": await channel_count(db),
        "issue": session.issue,
    }


async def latest_session(db: AsyncSession, user_id: int, *, lock: bool = False) -> TelegramVerificationSession | None:
    query = (
        select(TelegramVerificationSession)
        .where(TelegramVerificationSession.user_id == user_id)
        .order_by(TelegramVerificationSession.id.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def open_session(db: AsyncSession, user: User) -> dict:
    """Return the user's open session, or start a new one on a healthy bot.

    An open session whose bot has since failed or been switched off is
    replaced, so the user isn't left with a link nobody answers.
    """
    if user.status == "ACTIVE":
        raise errors.AlreadyVerified()
    if user.status != "PENDING_VERIFICATION":
        raise errors.AccountSuspended()
    current = await latest_session(db, user.id, lock=True)
    if current is not None and is_open(current) and await bots.can_serve(db, current.bot_id):
        return await session_json(db, current)

    await ratelimit.hit(ratelimit.VERIFICATION_SESSIONS, user.id)
    bot = await bots.pick_verifier(db)
    if bot is None:
        raise errors.VerificationUnavailable()
    if current is not None and current.status in OPEN_SESSION_STATUSES:
        current.status = "EXPIRED"
        await db.flush()

    settings = await campaign.app_settings(db)
    at = timeutil.now()
    session = TelegramVerificationSession(
        user_id=user.id,
        bot_id=bot.id,
        status="OPEN",
        expires_at=at + timedelta(minutes=settings.verification_session_minutes),
    )
    db.add(session)
    await db.flush()
    session.token_hash = token_hash(start_token(session.id))
    # Keep the pending account alive while this session can still finish.
    locked_user = (await db.execute(select(User).where(User.id == user.id).with_for_update())).scalar_one()
    if locked_user.pending_expires_at is None or locked_user.pending_expires_at < session.expires_at:
        locked_user.pending_expires_at = session.expires_at
    await db.flush()
    await audit.record(db, f"user:{user.public_id}", "verification.session_opened", f"user:{user.public_id}")
    return await session_json(db, session)


async def current_session(db: AsyncSession, user: User) -> dict:
    session = await latest_session(db, user.id)
    if session is None:
        raise errors.NotFound()
    return await session_json(db, session)


async def find_by_token(db: AsyncSession, token: str) -> TelegramVerificationSession | None:
    if not token.startswith(TOKEN_PREFIX) or len(token) > 64:
        return None
    return (
        await db.execute(
            select(TelegramVerificationSession)
            .where(TelegramVerificationSession.token_hash == token_hash(token))
            .with_for_update()
        )
    ).scalar_one_or_none()


class Outcome(enum.Enum):
    VERIFIED = "VERIFIED"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"
    TELEGRAM_ALREADY_LINKED = "TELEGRAM_ALREADY_LINKED"
    SESSION_CLOSED = "SESSION_CLOSED"


async def complete(
    db: AsyncSession, session: TelegramVerificationSession, telegram_user_id: int, channel_states: list[dict]
) -> Outcome:
    """Activate the account. Safe to call twice: the second call changes nothing."""
    user = (await db.execute(select(User).where(User.id == session.user_id).with_for_update())).scalar_one()
    if user.status == "ACTIVE":
        return Outcome.ALREADY_VERIFIED
    if user.status != "PENDING_VERIFICATION" or not is_open(session):
        return Outcome.SESSION_CLOSED
    linked = (
        await db.execute(select(User.id).where(User.telegram_user_id == telegram_user_id, User.id != user.id))
    ).scalar_one_or_none()
    if linked is not None:
        session.issue = "TELEGRAM_ALREADY_LINKED"
        return Outcome.TELEGRAM_ALREADY_LINKED

    at = timeutil.now()
    user.status = "ACTIVE"
    user.verified_at = at
    user.telegram_user_id = telegram_user_id
    user.pending_expires_at = None
    user.updated_at = at
    session.status = "COMPLETED"
    session.completed_at = at
    session.issue = None
    db.add(
        TelegramVerification(
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            session_id=session.id,
            bot_id=session.bot_id,
            channel_states=channel_states,
            verified_at=at,
        )
    )
    await db.execute(
        update(MembershipCounter)
        .where(MembershipCounter.id == 1)
        .values(verified_count=MembershipCounter.verified_count + 1, updated_at=at)
    )
    await db.flush()
    await referrals.qualify(db, user)
    await rewards.credit_for_verified_user(db, user)
    await risk.after_verification(db, user)
    await audit.record(db, "telegram", "user.verified", f"user:{user.public_id}", {"channels": channel_states})
    return Outcome.VERIFIED

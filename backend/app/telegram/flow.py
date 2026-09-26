"""The verification conversation.

Handlers run inside a database transaction and return the messages to send;
the webhook sends them after the transaction commits.

Verifier bot, per user:
  /start <token>  → bind the Telegram account to the session, show JOIN buttons
  "I've sent the requests" → check each required channel, then ask for contact
  contact         → must be the sender's own contact; compare with signup phone

Watcher bot (admin in the required channels):
  chat_join_request → record it. Requests are never approved automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.models import RequiredChannel, TelegramBot, TelegramJoinRequest, TelegramVerificationSession, User
from app.phone import normalize_indian_mobile
from app.security import ratelimit
from app.services import audit, bots, campaign, verification
from app.services.verification import Outcome
from app.telegram import texts
from app.telegram.client import TelegramError

log = logging.getLogger("telegram")

MEMBER_STATUSES = {"creator", "administrator", "member"}


@dataclass
class Outgoing:
    method: str
    params: dict[str, Any] = field(default_factory=dict)


def _send(chat_id: int, text: str, markup: dict | None = None) -> Outgoing:
    return Outgoing("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": markup})


def _join_keyboard(channels: list[RequiredChannel]) -> dict:
    buttons = [{"text": f"JOIN {i}", "url": ch.invite_link} for i, ch in enumerate(channels, 1)]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([{"text": texts.CHECK_BUTTON, "callback_data": texts.CHECK_CALLBACK}])
    return {"inline_keyboard": rows}


CONTACT_KEYBOARD = {
    "keyboard": [[{"text": texts.CONTACT_BUTTON, "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
REMOVE_KEYBOARD = {"remove_keyboard": True}


async def _channels(db: AsyncSession) -> list[RequiredChannel]:
    return list(
        (
            await db.execute(
                select(RequiredChannel).where(RequiredChannel.active).order_by(RequiredChannel.sort_order, RequiredChannel.id)
            )
        ).scalars()
    )


async def check_channels(db: AsyncSession, telegram_user_id: int) -> tuple[list[dict], list[RequiredChannel]]:
    """Which required channels this Telegram user has satisfied, and how.

    A recorded join request counts only if the admin setting allows pending
    requests. Membership is checked through the watcher bot, which covers
    people who had already joined before verifying.
    """
    settings = await campaign.app_settings(db)
    channels = await _channels(db)
    requested = set(
        (
            await db.execute(select(TelegramJoinRequest.chat_id).where(TelegramJoinRequest.telegram_user_id == telegram_user_id))
        ).scalars()
    )
    watcher = await bots.watcher(db)
    states: list[dict] = []
    missing: list[RequiredChannel] = []
    for channel in channels:
        if settings.accept_pending_join_requests and channel.chat_id in requested:
            states.append({"channel": channel.title, "state": "PENDING_REQUEST"})
            continue
        if watcher is not None:
            try:
                member = await bots.call(watcher, "getChatMember", chat_id=channel.chat_id, user_id=telegram_user_id)
                status = member.get("status")
                if status in MEMBER_STATUSES or (status == "restricted" and member.get("is_member")):
                    states.append({"channel": channel.title, "state": "MEMBER"})
                    continue
            except TelegramError:
                log.warning("membership check failed", extra={"channel_id": channel.id})
        missing.append(channel)
    return states, missing


async def _session_for(db: AsyncSession, bot: TelegramBot, telegram_user_id: int) -> TelegramVerificationSession | None:
    return (
        await db.execute(
            select(TelegramVerificationSession)
            .where(
                TelegramVerificationSession.telegram_user_id == telegram_user_id,
                TelegramVerificationSession.bot_id == bot.id,
                TelegramVerificationSession.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(TelegramVerificationSession.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()


async def _is_verified_telegram_user(db: AsyncSession, telegram_user_id: int) -> bool:
    return (await db.execute(select(User.id).where(User.telegram_user_id == telegram_user_id))).first() is not None


async def _on_start(db: AsyncSession, bot: TelegramBot, company: str, tg_id: int, token: str) -> list[Outgoing]:
    session = await verification.find_by_token(db, token) if token else None
    if session is None or session.bot_id != bot.id or not verification.is_open(session):
        if await _is_verified_telegram_user(db, tg_id):
            return [_send(tg_id, texts.already_verified(company))]
        return [_send(tg_id, texts.start_invalid(company))]
    if session.telegram_user_id != tg_id:
        # First open, or the user switched Telegram accounts: start over with
        # this account. The contact check still decides the outcome.
        session.telegram_user_id = tg_id
        session.channels_confirmed_at = None
    session.status = "IN_PROGRESS"
    session.issue = None
    return await _next_step(db, company, session, tg_id)


async def _next_step(db: AsyncSession, company: str, session: TelegramVerificationSession, tg_id: int) -> list[Outgoing]:
    channels = await _channels(db)
    if session.channels_confirmed_at is None and channels:
        return [_send(tg_id, texts.welcome(company, [c.title for c in channels]), _join_keyboard(channels))]
    if session.channels_confirmed_at is None:
        session.channels_confirmed_at = timeutil.now()
    return [_send(tg_id, texts.contact_ask(), CONTACT_KEYBOARD)]


async def _on_check(db: AsyncSession, bot: TelegramBot, company: str, tg_id: int) -> list[Outgoing]:
    session = await _session_for(db, bot, tg_id)
    if session is None or not verification.is_open(session):
        return [_send(tg_id, texts.no_session(company))]
    states, missing = await check_channels(db, tg_id)
    if missing:
        session.issue = "CHANNELS_MISSING"
        return [_send(tg_id, texts.channels_missing([c.title for c in missing]), _join_keyboard(missing))]
    session.channels_confirmed_at = timeutil.now()
    session.issue = None
    return [_send(tg_id, texts.contact_ask(), CONTACT_KEYBOARD)]


async def _on_contact(db: AsyncSession, bot: TelegramBot, company: str, tg_id: int, contact: dict) -> list[Outgoing]:
    session = await _session_for(db, bot, tg_id)
    if session is None or not verification.is_open(session):
        if await _is_verified_telegram_user(db, tg_id):
            return [_send(tg_id, texts.already_verified(company), REMOVE_KEYBOARD)]
        return [_send(tg_id, texts.no_session(company), REMOVE_KEYBOARD)]
    if session.channels_confirmed_at is None:
        return await _next_step(db, company, session, tg_id)
    # Only the sender's own contact proves they hold the number. A forwarded
    # contact card of someone else has a different user_id (or none).
    if contact.get("user_id") != tg_id:
        return [_send(tg_id, texts.contact_not_own(), CONTACT_KEYBOARD)]

    # Channels are re-checked at the moment of completion: requests can be
    # cancelled, and membership can change.
    states, missing = await check_channels(db, tg_id)
    if missing:
        session.channels_confirmed_at = None
        session.issue = "CHANNELS_MISSING"
        return [
            _send(tg_id, texts.channels_missing([c.title for c in missing]), _join_keyboard(missing)),
        ]

    user = await db.get(User, session.user_id)
    assert user is not None
    shared = normalize_indian_mobile(contact.get("phone_number"))
    if shared is None or shared != user.phone:
        settings = await campaign.app_settings(db)
        session.mismatch_count += 1
        await audit.record(db, "telegram", "verification.phone_mismatch", f"user:{user.public_id}")
        if session.mismatch_count >= settings.max_contact_mismatches:
            session.status = "FAILED"
            session.issue = "PHONE_MISMATCH_LIMIT"
            return [_send(tg_id, texts.mismatch_limit(company), REMOVE_KEYBOARD)]
        session.issue = "PHONE_MISMATCH"
        left = settings.max_contact_mismatches - session.mismatch_count
        return [_send(tg_id, texts.mismatch(company, left), CONTACT_KEYBOARD)]

    outcome = await verification.complete(db, session, tg_id, states)
    if outcome in (Outcome.VERIFIED, Outcome.ALREADY_VERIFIED):
        return [_send(tg_id, texts.verified(company), REMOVE_KEYBOARD)]
    if outcome is Outcome.TELEGRAM_ALREADY_LINKED:
        return [_send(tg_id, texts.linked_elsewhere(company), REMOVE_KEYBOARD)]
    return [_send(tg_id, texts.start_invalid(company), REMOVE_KEYBOARD)]


async def handle_verifier(db: AsyncSession, bot: TelegramBot, update: dict) -> list[Outgoing]:
    company = (await campaign.app_settings(db)).company_name
    callback = update.get("callback_query")
    message = update.get("message")
    sender = (callback or message or {}).get("from") or {}
    tg_id = sender.get("id")
    if not isinstance(tg_id, int) or sender.get("is_bot"):
        return []
    if (message or {}).get("chat", {}).get("type", "private") != "private":
        return []  # the bots only talk in private chats

    try:
        await ratelimit.hit(ratelimit.TELEGRAM_MESSAGES, tg_id)
    except errors.RateLimited:
        return []  # flooding: stop answering until the window passes

    if callback is not None:
        out: list[Outgoing] = [Outgoing("answerCallbackQuery", {"callback_query_id": callback["id"]})]
        if callback.get("data") == texts.CHECK_CALLBACK:
            out += await _on_check(db, bot, company, tg_id)
        return out

    assert message is not None
    if message.get("contact"):
        return await _on_contact(db, bot, company, tg_id, message["contact"])
    text = (message.get("text") or "").strip()
    if text.startswith("/start"):
        token = text[len("/start") :].strip()
        return await _on_start(db, bot, company, tg_id, token)

    session = await _session_for(db, bot, tg_id)
    if session is not None and verification.is_open(session):
        return await _next_step(db, company, session, tg_id)
    if await _is_verified_telegram_user(db, tg_id):
        return [_send(tg_id, texts.already_verified(company))]
    return [_send(tg_id, texts.no_session(company))]


async def handle_watcher(db: AsyncSession, bot: TelegramBot, update: dict) -> list[Outgoing]:
    request = update.get("chat_join_request")
    if not request:
        return []
    chat_id = (request.get("chat") or {}).get("id")
    tg_id = (request.get("from") or {}).get("id")
    if not isinstance(chat_id, int) or not isinstance(tg_id, int):
        return []
    known = (await db.execute(select(RequiredChannel.id).where(RequiredChannel.chat_id == chat_id))).first()
    if known is None:
        return []
    raw_date = request.get("date")
    requested_at = datetime.fromtimestamp(raw_date, tz=UTC) if isinstance(raw_date, int) else timeutil.now()
    stmt = insert(TelegramJoinRequest).values(telegram_user_id=tg_id, chat_id=chat_id, requested_at=requested_at)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[TelegramJoinRequest.telegram_user_id, TelegramJoinRequest.chat_id],
            set_={"requested_at": stmt.excluded.requested_at},
        )
    )
    return []

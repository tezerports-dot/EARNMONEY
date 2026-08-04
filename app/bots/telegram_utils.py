"""Thin helpers over the Bot API: retries, invite links, cross-chat bans."""

from __future__ import annotations

import asyncio
import html
import logging
import sqlite3
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from app import db

log = logging.getLogger("bots.telegram")

T = TypeVar("T")

# Telegram allows ~20 messages/minute to a group and ~30 messages/second
# overall. Broadcasts and DM sweeps pace themselves with this delay.
BROADCAST_DELAY = 0.35


def esc(value: Any) -> str:
    """HTML-escape a value for parse_mode=HTML messages."""
    return html.escape(str(value if value is not None else ""), quote=False)


async def call_api(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    retries: int = 4,
    **kwargs: Any,
) -> T | None:
    """Call a Bot API method, honouring 429 back-off.

    Returns ``None`` instead of raising when Telegram refuses permanently
    (bot removed, chat gone, user blocked the bot) so a single dead chat never
    aborts a sweep over hundreds of them.
    """
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as exc:
            wait = float(getattr(exc, "retry_after", delay)) + 0.5
            log.warning("rate limited, sleeping %.1fs (attempt %d)", wait, attempt + 1)
            await asyncio.sleep(wait)
        except TelegramNetworkError as exc:
            if attempt >= retries:
                log.warning("network error, giving up: %s", exc)
                return None
            await asyncio.sleep(delay)
            delay *= 2
        except TelegramForbiddenError as exc:
            log.info("forbidden: %s", exc)
            return None
        except TelegramBadRequest as exc:
            log.info("bad request: %s", exc)
            return None
    return None


def bot_for_chat(chat_id: int) -> Bot | None:
    """A running bot instance that is registered in ``chat_id``."""
    from app.bots.manager import manager

    for row in db.chat_rows(int(chat_id)):
        bot = manager.get_bot(int(row["bot_id"]))
        if bot is not None:
            return bot
    return None


async def ensure_personal_invite(bot: Bot, chat_id: int, uid: str) -> str | None:
    """Create a named invite link that identifies its owner on join.

    ``creates_join_request=True`` means a tap produces a join request the bot
    approves automatically — the closest thing to "auto-add" the Bot API
    offers, since no bot can add a user to a chat by itself.

    The link is *named* after the UID, which is what Telegram reports back on
    join, so attribution needs nothing stored anywhere.
    """
    link = await call_api(
        bot.create_chat_invite_link,
        chat_id=int(chat_id),
        name=uid[:32],
        creates_join_request=True,
    )
    if link is None:
        # Some chats reject join-request links (e.g. the bot lacks the right).
        # Fall back to a plain named link, which still reports the link used.
        link = await call_api(
            bot.create_chat_invite_link, chat_id=int(chat_id), name=uid[:32]
        )
    return link.invite_link if link is not None else None


async def ban_everywhere(user_id: int, reason: str = "") -> list[int]:
    """Ban a user from every managed chat. Returns the chats acted on."""
    done: list[int] = []
    for row in db.distinct_managed_chats():
        chat_id = int(row["chat_id"])
        bot = bot_for_chat(chat_id)
        if bot is None:
            continue
        result = await call_api(bot.ban_chat_member, chat_id=chat_id, user_id=user_id)
        if result:
            done.append(chat_id)
            db.set_membership(user_id, chat_id, False)
        await asyncio.sleep(0.1)
    db.set_flags(user_id, banned=True)
    db.log_event("ban", user_id, f"{reason} chats={len(done)}")
    return done


async def unban_everywhere(user_id: int) -> list[int]:
    done: list[int] = []
    for row in db.distinct_managed_chats():
        chat_id = int(row["chat_id"])
        bot = bot_for_chat(chat_id)
        if bot is None:
            continue
        result = await call_api(
            bot.unban_chat_member, chat_id=chat_id, user_id=user_id, only_if_banned=True
        )
        if result:
            done.append(chat_id)
        await asyncio.sleep(0.1)
    db.set_flags(user_id, banned=False)
    db.log_event("unban", user_id, f"chats={len(done)}")
    return done


async def notify_admins(text: str, exclude: int | None = None) -> None:
    """Send an operational notice to every configured admin, via any bot."""
    from app.bots.manager import manager
    from app.config import settings

    bot = manager.any_bot()
    if bot is None:
        return
    for admin_id in settings.admin_ids:
        if exclude is not None and admin_id == exclude:
            continue
        await call_api(bot.send_message, chat_id=admin_id, text=text)
        await asyncio.sleep(0.05)


async def copy_to_chats(
    bot: Bot,
    from_chat_id: int,
    message_id: int,
    chat_ids: Iterable[int],
) -> tuple[list[int], list[tuple[int, str]]]:
    """Copy one message into many chats. Returns ``(delivered, failures)``.

    Each chat is served by a bot that is actually an admin there, so a fleet
    where different bots cover different chats still gets full coverage from a
    single owner message.
    """
    delivered: list[int] = []
    failures: list[tuple[int, str]] = []
    for chat_id in chat_ids:
        target = bot_for_chat(chat_id) or bot
        try:
            result = await call_api(
                target.copy_message,
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
        except Exception as exc:  # noqa: BLE001 - never abort a broadcast
            failures.append((chat_id, str(exc)[:120]))
            continue
        if result is None:
            failures.append((chat_id, "rejected by Telegram (rights or chat gone)"))
        else:
            delivered.append(chat_id)
        await asyncio.sleep(BROADCAST_DELAY)
    return delivered, failures


async def send_to_chats(
    text: str,
    chat_ids: Iterable[int],
    reply_markup: Any = None,
) -> tuple[list[int], list[tuple[int, str]]]:
    """Send the same text into many chats, one bot per chat."""
    delivered: list[int] = []
    failures: list[tuple[int, str]] = []
    for chat_id in chat_ids:
        bot = bot_for_chat(chat_id)
        if bot is None:
            failures.append((chat_id, "no running bot registered in this chat"))
            continue
        result = await call_api(
            bot.send_message, chat_id=chat_id, text=text, reply_markup=reply_markup
        )
        if result is None:
            failures.append((chat_id, "rejected by Telegram (rights or chat gone)"))
        else:
            delivered.append(chat_id)
        await asyncio.sleep(BROADCAST_DELAY)
    return delivered, failures


async def check_admin_rights(bot: Bot, bot_id: int) -> list[str]:
    """Verify the bot is an admin able to invite users in each of its chats."""
    problems: list[str] = []
    me = await call_api(bot.get_me)
    if me is None:
        return ["could not reach Telegram"]
    for row in db.list_chats(bot_id):
        chat_id = int(row["chat_id"])
        member = await call_api(bot.get_chat_member, chat_id=chat_id, user_id=me.id)
        title = row["title"] or chat_id
        if member is None:
            problems.append(f"{title}: not reachable (bot removed or chat deleted)")
            continue
        if member.status != "administrator":
            problems.append(f"{title}: bot is '{member.status}', needs to be an administrator")
            continue
        if not getattr(member, "can_invite_users", False):
            problems.append(f"{title}: admin without the 'invite users' right")
    return problems


def user_label(user: sqlite3.Row | None) -> str:
    if user is None:
        return "unknown"
    name = user["full_name"] or user["username"] or user["id"]
    return f"{esc(name)} ({user['uid']})"

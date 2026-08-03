"""Moderation bot: behaviour rules and bans across every managed chat.

Rules are data, not code — thresholds and word lists live in the ``settings``
table and are editable from the admin panel without a restart.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque

from aiogram import Bot, F
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, Message

from app import db
from app.bots.routerspec import RouterSpec
from app.bots.common import ensure_user, is_owner
from app.bots.telegram_utils import ban_everywhere, call_api, esc, unban_everywhere
from app.timeutil import now_utc

log = logging.getLogger("bots.moderation")

router = RouterSpec("moderation")

LINK_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z][A-Za-z0-9_]{4,})")

# (chat_id, user_id) -> timestamps of recent messages, for flood detection.
_recent: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=32))


def _banned_words() -> list[str]:
    raw = db.get_setting("banned_words", "")
    return [word.strip().lower() for word in raw.split(",") if word.strip()]


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    if is_owner(user_id):
        return True
    member = await call_api(bot.get_chat_member, chat_id=chat_id, user_id=user_id)
    return member is not None and member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }


async def _mute(bot: Bot, chat_id: int, user_id: int, minutes: int) -> bool:
    until = int(now_utc().timestamp()) + minutes * 60
    result = await call_api(
        bot.restrict_chat_member,
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    return result is not None


async def _punish(bot: Bot, message: Message, user_id: int, reason: str) -> None:
    """Warn, then mute, then ban — thresholds come from settings."""
    chat_id = message.chat.id
    count = db.add_warning(user_id, chat_id)
    mute_at = db.get_setting_int("warn_mute_at", 3)
    ban_at = db.get_setting_int("warn_ban_at", 5)
    mute_minutes = db.get_setting_int("mute_minutes", 60)

    db.log_event("moderation_warn", user_id, f"chat={chat_id} reason={reason} count={count}")

    if count >= ban_at:
        await ban_everywhere(user_id, reason=f"{reason} ({count} warnings)")
        await call_api(
            bot.send_message,
            chat_id=chat_id,
            text=(
                f"🚫 Banned from all managed chats after {count} warnings "
                f"(<code>{user_id}</code>). Reason: {esc(reason)}."
            ),
        )
        return

    if count >= mute_at:
        if await _mute(bot, chat_id, user_id, mute_minutes):
            await call_api(
                bot.send_message,
                chat_id=chat_id,
                text=(
                    f"🔇 Muted for {mute_minutes} minutes — warning {count}/{ban_at}. "
                    f"Reason: {esc(reason)}."
                ),
            )
            return

    await call_api(
        bot.send_message,
        chat_id=chat_id,
        text=f"⚠️ Warning {count}/{ban_at}. Reason: {esc(reason)}.",
    )


async def watch_group(message: Message, bot: Bot) -> None:
    """Screen every group message against the configured rules.

    Deliberately *not* decorated: this matches every group message, and the
    first matching handler wins, so it is registered at the bottom of this
    module — after the moderation commands, which would otherwise never fire.
    """
    if message.from_user is None or message.from_user.is_bot:
        return
    if not db.get_setting_bool("moderation_enabled", True):
        return
    if not db.chat_rows(message.chat.id):
        return

    user = ensure_user(message.from_user)
    user_id = int(user["id"])

    if user["banned"] or user["duplicate"]:
        await call_api(bot.delete_message, chat_id=message.chat.id, message_id=message.message_id)
        await call_api(bot.ban_chat_member, chat_id=message.chat.id, user_id=user_id)
        db.set_membership(user_id, message.chat.id, "group", "banned")
        return

    if await _is_chat_admin(bot, message.chat.id, user_id):
        return

    text = (message.text or message.caption or "").strip()

    words = _banned_words()
    lowered = text.lower()
    if words and any(word in lowered for word in words):
        await call_api(bot.delete_message, chat_id=message.chat.id, message_id=message.message_id)
        await _punish(bot, message, user_id, "forbidden word")
        return

    if (
        db.get_setting_bool("block_links_from_unverified", True)
        and not user["verified"]
        and (LINK_RE.search(text) or message.forward_origin is not None)
    ):
        await call_api(bot.delete_message, chat_id=message.chat.id, message_id=message.message_id)
        await _punish(
            bot,
            message,
            user_id,
            "links and forwards are not allowed before you verify with the main bot",
        )
        return

    limit = db.get_setting_int("flood_limit", 6)
    window = db.get_setting_int("flood_window_seconds", 8)
    bucket = _recent[(message.chat.id, user_id)]
    now = time.monotonic()
    bucket.append(now)
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) > limit:
        bucket.clear()
        await _punish(bot, message, user_id, f"flooding ({limit}+ messages in {window}s)")


def _target_id(message: Message, command: CommandObject) -> int | None:
    """Resolve the user a moderation command applies to."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return int(message.reply_to_message.from_user.id)
    arg = (command.args or "").strip()
    if not arg:
        return None
    if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
        return int(arg)
    from app.ids import normalise_uid

    uid = normalise_uid(arg)
    if uid:
        row = db.get_user_by_uid(uid)
        if row is not None:
            return int(row["id"])
    handle = arg.lstrip("@").lower()
    row = db.query_one("SELECT id FROM users WHERE LOWER(username) = ?", (handle,))
    return int(row["id"]) if row else None


async def _guard(message: Message, bot: Bot) -> bool:
    if message.from_user is None:
        return False
    if not await _is_chat_admin(bot, message.chat.id, int(message.from_user.id)):
        await message.reply("Only chat admins can use this command.")
        return False
    return True


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/ban UID-XXXXXX</code>.")
        return
    chats = await ban_everywhere(target, reason=f"manual ban by {message.from_user.id}")
    await message.reply(f"🚫 Banned <code>{target}</code> from {len(chats)} chat(s).")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/unban UID-XXXXXX</code>.")
        return
    chats = await unban_everywhere(target)
    db.reset_warnings(target)
    await message.reply(f"✅ Unbanned <code>{target}</code> in {len(chats)} chat(s).")


@router.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    parts = (command.args or "").split()
    minutes = db.get_setting_int("mute_minutes", 60)
    if parts and parts[-1].isdigit():
        minutes = int(parts[-1])
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/mute UID-XXXXXX 30</code>.")
        return
    if await _mute(bot, message.chat.id, target, minutes):
        db.log_event("moderation_mute", target, f"chat={message.chat.id} minutes={minutes}")
        await message.reply(f"🔇 Muted <code>{target}</code> for {minutes} minutes.")
    else:
        await message.reply("Could not mute — check my admin rights.")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/unmute UID-XXXXXX</code>.")
        return
    result = await call_api(
        bot.restrict_chat_member,
        chat_id=message.chat.id,
        user_id=target,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True,
        ),
    )
    await message.reply(
        f"🔊 Unmuted <code>{target}</code>." if result else "Could not unmute — check my rights."
    )


@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/warn UID-XXXXXX</code>.")
        return
    await _punish(bot, message, target, "manual warning")


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    if target is None:
        await message.reply("Reply to someone, or use <code>/unwarn UID-XXXXXX</code>.")
        return
    db.reset_warnings(target, message.chat.id)
    await message.reply(f"✅ Warnings cleared for <code>{target}</code> in this chat.")


@router.message(Command("whois"))
async def cmd_whois(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _guard(message, bot):
        return
    target = _target_id(message, command)
    user = db.get_user(target) if target else None
    if user is None:
        await message.reply("No record for that user.")
        return
    from app.earnings import status_for

    st = status_for(user)
    await message.reply(
        f"🆔 <code>{esc(user['uid'])}</code>\n"
        f"Telegram id: <code>{user['id']}</code>\n"
        f"Verified: {'yes' if user['verified'] else 'no'} · "
        f"Duplicate: {'yes' if user['duplicate'] else 'no'} · "
        f"Banned: {'yes' if user['banned'] else 'no'}\n"
        f"Referred by: {esc(user['referred_by_uid'] or '-')}\n"
        f"Messages: {user['message_count']} · Warnings here: "
        f"{db.warning_count(int(user['id']), message.chat.id)}\n"
        f"This month: {st.interactions} interaction(s) — {esc(st.reason)}"
    )


@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start_private(message: Message) -> None:
    from app.bots.common import main_bot_link

    link = await main_bot_link()
    tail = f"\n\n👉 {link}" if link else ""
    await message.answer(
        "🛡️ I am the moderation bot — I keep the groups clean and enforce bans.\n\n"
        "To register, get your ID and your referral link, use the main bot." + tail
    )


# Registered last on purpose — see the docstring on watch_group.
router.message.register(
    watch_group, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
)

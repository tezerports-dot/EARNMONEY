"""Broadcast bot: the owner sends one message, every managed chat gets it.

Anything works — text, photo, video, document, forwarded post — because the
relay uses ``copyMessage`` rather than re-typing the content. Each chat is
served by a bot that is actually an administrator there, so one owner message
covers chats spread across several bots.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app import db
from app.bots.routerspec import RouterSpec
from app.bots.common import is_owner
from app.bots.telegram_utils import (
    call_api,
    copy_to_chats,
    esc,
    send_to_chats,
)

log = logging.getLogger("bots.broadcast")

router = RouterSpec("broadcast")
router.message.filter(F.chat.type == ChatType.PRIVATE)


def _targets(kind: str = "all") -> list[int]:
    rows = db.distinct_managed_chats()
    if kind == "groups":
        rows = [row for row in rows if row["chat_type"] == "group"]
    elif kind == "channels":
        rows = [row for row in rows if row["chat_type"] == "channel"]
    return [int(row["chat_id"]) for row in rows]


def _confirm_keyboard(message_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📢 Send to {count} chat(s)", callback_data=f"bcast:go:{message_id}"
                )
            ],
            [InlineKeyboardButton(text="✖ Cancel", callback_data="bcast:cancel")],
        ]
    )


async def _deliver(bot: Bot, owner_chat_id: int, message_id: int, report_to) -> None:
    targets = _targets()
    if not targets:
        await report_to("No chats are registered yet. Add them in the admin panel first.")
        return
    delivered, failures = await copy_to_chats(bot, owner_chat_id, message_id, targets)
    db.log_event(
        "broadcast", owner_chat_id, f"delivered={len(delivered)} failed={len(failures)}"
    )
    text = f"✅ Delivered to <b>{len(delivered)}</b> of {len(targets)} chat(s)."
    if failures:
        detail = "\n".join(f"• <code>{cid}</code> — {esc(err)}" for cid, err in failures[:10])
        text += f"\n\n⚠️ {len(failures)} failed:\n{detail}"
    await report_to(text)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return
    if not is_owner(message.from_user.id):
        from app.bots.common import main_bot_link

        link = await main_bot_link()
        tail = f"\n\n👉 {link}" if link else ""
        await message.answer(
            "📢 I only relay announcements from the owners.\n\n"
            "To register and get your referral link, use the main bot." + tail
        )
        return
    await message.answer(
        "📢 <b>Broadcast bot</b>\n\n"
        "Send me anything — text, photo, video, document, a forwarded post — "
        "and I will copy it into every managed group and channel.\n\n"
        "<b>Commands</b>\n"
        "/targets — list the chats I will post to\n"
        "/poll Question | Option A | Option B — post a poll to every group "
        "(only polls I create can be counted as activity)\n"
        "/confirm on|off — ask before sending (currently "
        f"<b>{'on' if db.get_setting_bool('broadcast_confirm', True) else 'off'}</b>)"
    )


@router.message(Command("targets"))
async def cmd_targets(message: Message) -> None:
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    rows = db.distinct_managed_chats()
    if not rows:
        await message.answer("No chats registered yet.")
        return
    lines = [f"📋 <b>{len(rows)} managed chat(s)</b>", ""]
    for row in rows:
        icon = "📢" if row["chat_type"] == "channel" else "👥"
        lines.append(
            f"{icon} {esc(row['title'] or 'untitled')} — <code>{row['chat_id']}</code>"
        )
    await message.answer("\n".join(lines))


@router.message(Command("confirm"))
async def cmd_confirm(message: Message, command: CommandObject) -> None:
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    arg = (command.args or "").strip().lower()
    if arg not in {"on", "off"}:
        await message.answer("Use <code>/confirm on</code> or <code>/confirm off</code>.")
        return
    db.set_setting("broadcast_confirm", "1" if arg == "on" else "0")
    await message.answer(
        f"Confirmation is now <b>{arg}</b>."
        + (" I will send immediately from now on." if arg == "off" else "")
    )


@router.message(Command("poll"))
async def cmd_poll(message: Message, command: CommandObject) -> None:
    """Post a bot-created poll into every managed group.

    Telegram delivers ``poll_answer`` only for polls the bot itself created,
    so this is the only kind of poll that can ever count as activity.
    """
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    parts = [part.strip() for part in (command.args or "").split("|") if part.strip()]
    if len(parts) < 3:
        await message.answer(
            "Usage: <code>/poll Are you active this month? | Yes | Not yet</code>\n"
            "(one question and at least two options)"
        )
        return
    question, options = parts[0], parts[1:10]

    delivered, failed = 0, 0
    for row in db.distinct_managed_chats():
        if row["chat_type"] != "group":
            continue
        from app.bots.telegram_utils import bot_for_chat

        target = bot_for_chat(int(row["chat_id"]))
        if target is None:
            failed += 1
            continue
        result = await call_api(
            target.send_poll,
            chat_id=int(row["chat_id"]),
            question=question[:300],
            options=[opt[:100] for opt in options],
            is_anonymous=False,
        )
        if result is None:
            failed += 1
        else:
            delivered += 1
    db.log_event("broadcast_poll", message.from_user.id, f"ok={delivered} failed={failed}")
    await message.answer(
        f"🗳 Poll posted to <b>{delivered}</b> group(s)"
        + (f", {failed} failed." if failed else ".")
        + "\n\nVotes on this poll count as monthly activity."
    )


@router.message(Command("say"))
async def cmd_say(message: Message, command: CommandObject) -> None:
    """Send plain text without the confirmation step."""
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: <code>/say your announcement here</code>")
        return
    targets = _targets()
    delivered, failures = await send_to_chats(text, targets)
    db.log_event("broadcast_say", message.from_user.id, f"ok={len(delivered)}")
    await message.answer(
        f"✅ Sent to <b>{len(delivered)}</b> of {len(targets)} chat(s)."
        + (f"\n⚠️ {len(failures)} failed." if failures else "")
    )


@router.message()
async def relay_anything(message: Message, bot: Bot) -> None:
    """Any other private message from an owner becomes a broadcast."""
    if message.from_user is None:
        return
    if not is_owner(message.from_user.id):
        return
    if (message.text or "").startswith("/"):
        await message.answer("Unknown command. Send /start to see what I can do.")
        return

    targets = _targets()
    if not targets:
        await message.answer("No chats are registered yet. Add them in the admin panel first.")
        return

    if db.get_setting_bool("broadcast_confirm", True):
        await message.answer(
            f"Send this to <b>{len(targets)}</b> managed chat(s)?",
            reply_markup=_confirm_keyboard(message.message_id, len(targets)),
        )
        return

    await _deliver(bot, message.chat.id, message.message_id, message.answer)


@router.callback_query(F.data.startswith("bcast:"))
async def on_confirm(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user is None or not is_owner(callback.from_user.id):
        await callback.answer("Not allowed.", show_alert=True)
        return
    if callback.message is None:
        await callback.answer()
        return

    action = (callback.data or "").split(":")
    if len(action) >= 2 and action[1] == "cancel":
        await callback.answer("Cancelled.")
        await callback.message.edit_text("✖ Broadcast cancelled — nothing was sent.")
        return

    if len(action) < 3 or not action[2].isdigit():
        await callback.answer()
        return

    await callback.answer("Sending…")
    await callback.message.edit_text("📤 Sending…")
    await _deliver(bot, callback.message.chat.id, int(action[2]), callback.message.answer)

"""Collector bot: the daily bank-details nudge.

The daily sweep itself is driven by the scheduler in :mod:`app.scheduler` so
it fires exactly once a day no matter how many bots are running. This router
only adds the manual controls.
"""

from __future__ import annotations

from aiogram import F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app import db
from app.bots.routerspec import RouterSpec
from app.bots.common import is_owner, main_bot_link
from app.bots.services import daily_bank_prompt
from app.bots.telegram_utils import esc
from app.config import settings

router = RouterSpec("collector")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return
    if is_owner(message.from_user.id):
        await message.answer(
            "🗂 <b>Collector bot</b>\n\n"
            f"Every day at {settings.daily_prompt_hour:02d}:00 IST I post the "
            "bank-details reminder in every managed chat, and DM every verified "
            "user who has not submitted theirs yet.\n\n"
            "<b>Commands</b>\n"
            "/prompt — run the daily sweep right now\n"
            "/prompttext &lt;text&gt; — change the message (HTML allowed)\n"
            "/pending — how many users still owe bank details"
        )
        return
    link = await main_bot_link()
    tail = f"\n\n👉 {link}" if link else ""
    await message.answer(
        "🗂 I only send reminders about bank details.\n\n"
        "Send /bank in the main bot to submit yours." + tail
    )


@router.message(Command("prompt"))
async def cmd_prompt(message: Message) -> None:
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    await message.answer("Running the daily sweep…")
    result = await daily_bank_prompt()
    await message.answer(
        f"✅ Posted in <b>{result['chats']}</b> chat(s), DMed <b>{result['dms']}</b> user(s)."
        + (f"\n⚠️ {result['failed']} chat(s) failed." if result["failed"] else "")
    )


@router.message(Command("prompttext"))
async def cmd_prompt_text(message: Message, command: CommandObject) -> None:
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(
            "Current message:\n\n" + db.get_setting("daily_prompt_text") +
            "\n\nUsage: <code>/prompttext your new message</code>"
        )
        return
    db.set_setting("daily_prompt_text", text)
    await message.answer("✅ Daily message updated. Preview:\n\n" + text)


@router.message(Command("pending"))
async def cmd_pending(message: Message) -> None:
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    pending = db.users_without_bank_details()
    total = db.count_users("verified = 1 AND duplicate = 0 AND banned = 0")
    lines = [
        f"🏦 <b>{len(pending)}</b> of {total} verified users have not submitted bank details.",
    ]
    if pending:
        lines.append("")
        for user in pending[:25]:
            name = user["full_name"] or user["username"] or user["id"]
            lines.append(f"• {esc(name)} — <code>{esc(user['uid'])}</code>")
        if len(pending) > 25:
            lines.append(f"… and {len(pending) - 25} more")
    await message.answer("\n".join(lines))

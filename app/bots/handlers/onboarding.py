"""Main bot: one tap turns a stranger into a placed, verified referrer."""

from __future__ import annotations

import logging
import sqlite3

from aiogram import Bot, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message, ReplyKeyboardRemove

from app import db
from app.bots.routerspec import RouterSpec
from app.bots.common import (
    contact_keyboard,
    dashboard_link,
    ensure_user,
    join_keyboard,
    menu_keyboard,
    referral_link,
    share_keyboard,
)
from app.bots.services import assign_pair_and_links, handle_duplicate
from app.bots.telegram_utils import esc
from app.earnings import rates
from app.ids import hash_phone, parse_referral_payload

log = logging.getLogger("bots.onboarding")

router = RouterSpec("onboarding")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("start"))
async def cmd_start(
    message: Message, command: CommandObject, bot: Bot, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    await state.clear()  # /start always escapes a half-finished form

    referrer_uid = parse_referral_payload(command.args)
    referrer = db.get_user_by_uid(referrer_uid) if referrer_uid else None

    existing = db.get_user(message.from_user.id)
    if referrer is not None and existing is not None and int(referrer["id"]) == int(existing["id"]):
        await message.answer("You cannot refer yourself 🙂 — share your link with someone else.")
        referrer = None
    if referrer is not None and (referrer["duplicate"] or referrer["banned"]):
        await message.answer("That referral link belongs to a blocked account, so it was ignored.")
        referrer = None
    if (
        referrer is not None
        and existing is not None
        and referrer["referred_by_uid"] == existing["uid"]
    ):
        # A refers B, then A opens B's link. Accepting it would make the two
        # of them each other's upline and each other's level-2 downline.
        await message.answer(
            "You already invited that member, so their link does not apply to you."
        )
        referrer = None

    user = ensure_user(
        message.from_user,
        referred_by_uid=str(referrer["uid"]) if referrer is not None else None,
    )

    if user["banned"] or user["duplicate"]:
        await message.answer(
            "🚫 This account is blocked. If you think that is a mistake, contact an admin."
        )
        return

    if user["verified"]:
        await send_account_card(message, bot, refresh_links=True)
        return

    intro = db.get_setting("welcome_text")
    if referrer is not None:
        intro += f"\n\n👤 You were invited by <b>{esc(referrer['uid'])}</b>."
    intro += (
        "\n\nThe button below shares your phone number with this bot. Your "
        "number is stored only as a one-way hash — it is used to make sure "
        "one person cannot register twice, and it is never shown to anyone."
    )
    await message.answer(intro, reply_markup=contact_keyboard())


@router.message(F.contact)
async def on_contact(message: Message, bot: Bot) -> None:
    """The single button: verify, place, issue links, hand back the ID."""
    contact: Contact | None = message.contact
    if contact is None or message.from_user is None:
        return

    if contact.user_id != message.from_user.id:
        await message.answer(
            "❌ That contact belongs to someone else. Please tap the button and "
            "share <b>your own</b> contact.",
            reply_markup=contact_keyboard(),
        )
        return

    user = ensure_user(message.from_user)
    user_id = int(user["id"])

    if user["banned"] or user["duplicate"]:
        await message.answer("🚫 This account is blocked.", reply_markup=ReplyKeyboardRemove())
        return

    try:
        phone_hash = hash_phone(contact.phone_number)
    except ValueError:
        await message.answer("❌ That phone number could not be read. Try again.")
        return

    owner = db.get_user_by_phone_hash(phone_hash)
    if owner is not None and int(owner["id"]) != user_id:
        await handle_duplicate(user, owner)
        await message.answer(
            "🚫 <b>This phone number is already registered</b> to another "
            f"account ({esc(owner['uid'])}).\n\nOne person may hold one account "
            "only, so this account has been blocked and removed from all "
            "groups and channels.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not user["verified"]:
        try:
            db.set_user_fields(user_id, phone_hash=phone_hash, verified=1)
        except sqlite3.IntegrityError:
            # Two accounts raced to claim the same number; the UNIQUE index on
            # phone_hash is the real arbiter, so the loser is the duplicate.
            owner = db.get_user_by_phone_hash(phone_hash)
            if owner is not None and int(owner["id"]) != user_id:
                await handle_duplicate(user, owner)
                await message.answer(
                    "🚫 This phone number is already registered to another "
                    "account, so this one has been blocked.",
                    reply_markup=ReplyKeyboardRemove(),
                )
            return
        db.log_event("verified", user_id, "contact shared")

    await message.answer("✅ Verified. Setting up your group, channel and referral link…",
                         reply_markup=ReplyKeyboardRemove())
    await send_account_card(message, bot, refresh_links=True, first_time=True)


async def send_account_card(
    message: Message,
    bot: Bot,
    refresh_links: bool = False,
    first_time: bool = False,
) -> None:
    """The user's ID, referral link and join links — the post-signup screen."""
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    if user is None:
        return

    group_link = channel_link = None
    pair = None
    if refresh_links and user["verified"]:
        pair, group_link, channel_link = await assign_pair_and_links(user)
        user = db.get_user(int(user["id"])) or user
    elif user["pair_id"]:
        pair = db.get_pair(int(user["pair_id"]))
        if pair is not None:
            group_link = db.get_invite_link(int(user["id"]), int(pair["group_chat_id"] or 0))
            channel_link = db.get_invite_link(int(user["id"]), int(pair["channel_chat_id"] or 0))

    link = await referral_link(bot, str(user["uid"]))
    header = "🎉 <b>You are in!</b>" if first_time else "👤 <b>Your account</b>"

    lines = [
        header,
        "",
        f"🆔 Your ID: <code>{esc(user['uid'])}</code>",
        f"🔗 Your referral link:\n<code>{esc(link)}</code>",
    ]
    if pair is not None:
        placement = pair["title"] or f"pair {pair['pair_id']}"
        lines.append(f"📍 Your set: <b>{esc(placement)}</b>")
    if group_link or channel_link:
        lines += [
            "",
            "Tap both buttons below to enter your group and channel. You are "
            "let in automatically — the links are personal to you.",
        ]
    else:
        lines += [
            "",
            "⚠️ No group/channel is available for you yet. An admin has been "
            "notified; you will get your links as soon as one is configured.",
        ]

    current = rates()
    lines += [
        "",
        "<b>How you earn — two levels</b>",
        f"• 🥇 <b>₹{current.level1:g}</b> for every person <b>you</b> invite.",
        f"• 🥈 <b>₹{current.level2:g}</b> for every person <b>they</b> invite.",
        f"  So one friend who brings in a friend is worth ₹{current.total:g} to you.",
        "• Each of them counts for a month only if they stay in <b>both</b> "
        "their group and their channel <b>and</b> interact with a bot at least "
        "once that month.",
        "• Membership alone does not count, and extra taps do not pay extra.",
        "• You must be in both chats and interact at least once yourself to be paid.",
    ]
    dash = dashboard_link(str(user["uid"]))
    if dash:
        lines.append(f"\n🌐 Public page: {esc(dash)}")

    await message.answer("\n".join(lines), reply_markup=join_keyboard(group_link, channel_link))
    await message.answer(
        "Use the menu below any time. Send /help to see every command.",
        reply_markup=menu_keyboard(),
    )
    if first_time:
        await message.answer("Share this to invite people:", reply_markup=share_keyboard(link))


@router.message(Command("link"))
async def cmd_link(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    if user is None or not user["verified"]:
        await message.answer(
            "You need to verify first — tap the button below.",
            reply_markup=contact_keyboard(),
        )
        return
    link = await referral_link(bot, str(user["uid"]))
    await message.answer(
        f"🔗 <b>Your referral link</b>\n<code>{esc(link)}</code>\n\n"
        f"🆔 Your ID: <code>{esc(user['uid'])}</code>",
        reply_markup=share_keyboard(link),
    )


@router.message(Command("me"))
async def cmd_me(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    if user is None or not user["verified"]:
        await message.answer(
            "You are not verified yet. Tap the button below to finish in one step.",
            reply_markup=contact_keyboard(),
        )
        return
    await send_account_card(message, bot)


@router.callback_query(F.data == "menu:link")
async def cb_link(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = db.get_user(callback.from_user.id)
    if user is None or not user["verified"]:
        await callback.message.answer(
            "Verify first — tap the button below.", reply_markup=contact_keyboard()
        )
        return
    link = await referral_link(bot, str(user["uid"]))
    await callback.message.answer(
        f"🔗 <b>Your referral link</b>\n<code>{esc(link)}</code>",
        reply_markup=share_keyboard(link),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Commands</b>\n"
        "/start — register or reopen your account card\n"
        "/me — your ID, links and placement\n"
        "/link — your referral link\n"
        "/earnings — this month's earnings and referral breakdown\n"
        "/bank — submit your bank details (once only)\n"
        "/withdraw — request this month's payout\n"
        "/help — this message"
    )

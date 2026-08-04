"""Shared helpers for handlers: user upsert, keyboards, link building."""

from __future__ import annotations

import sqlite3

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    User,
)

from app import db
from app.config import settings
from app.ids import referral_payload

CONTACT_BUTTON_TEXT = "📱 Tap once — share contact & join"


def is_owner(user_id: int | None) -> bool:
    return user_id is not None and int(user_id) in settings.admin_ids


def full_name_of(user: User | None) -> str:
    """The display name from the *live* update.

    Names are never stored — Telegram sends the current one with every
    update, so the bots read it from there and the database holds less
    personal data.
    """
    if user is None:
        return ""
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(part for part in parts if part).strip() or (user.username or "")


def ensure_user(tg_user: User, referred_by: str | None = None) -> sqlite3.Row:
    """Fetch or create the ``users`` row for a Telegram user.

    Someone who only ever posts in a managed group also gets a row (and a
    UID); they stay unverified until they share a contact, so they can never
    be counted or paid.
    """
    return db.create_user(user_id=tg_user.id, referred_by=referred_by)


async def referral_link(bot: Bot, uid: str) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}?start={referral_payload(uid)}"


def dashboard_link(uid: str) -> str:
    if not settings.public_base_url:
        return ""
    return f"{settings.public_base_url}/u/{uid}"


def contact_keyboard() -> ReplyKeyboardMarkup:
    """The single button that drives the whole onboarding."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CONTACT_BUTTON_TEXT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap the button below",
    )


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 My earnings", callback_data="menu:earnings"),
                InlineKeyboardButton(text="👥 My referrals", callback_data="menu:referrals"),
            ],
            [
                InlineKeyboardButton(text="🔗 My referral link", callback_data="menu:link"),
                InlineKeyboardButton(text="🏦 Bank details", callback_data="menu:bank"),
            ],
            [InlineKeyboardButton(text="💸 Request payout", callback_data="menu:withdraw")],
        ]
    )


def join_keyboard(group_link: str | None, channel_link: str | None) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if group_link:
        rows.append([InlineKeyboardButton(text="👥 Open your group", url=group_link)])
    if channel_link:
        rows.append([InlineKeyboardButton(text="📢 Open your channel", url=channel_link)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def share_keyboard(link: str) -> InlineKeyboardMarkup:
    share_url = (
        "https://t.me/share/url?url="
        + link
        + "&text="
        + "Join%20with%20my%20referral%20link"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📤 Share my link", url=share_url)]]
    )


async def main_bot_link() -> str:
    """Deep link to a running main bot, for the other bots to point at."""
    from app.bots.manager import manager

    username = await manager.main_bot_username()
    return f"https://t.me/{username}" if username else ""

"""Main bot: earnings, referral breakdown and payout requests."""

from __future__ import annotations

from aiogram import Bot, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import db
from app.bots.routerspec import RouterSpec
from app.bank import mask_account
from app.bots.common import contact_keyboard
from app.bots.telegram_utils import esc, notify_admins
from app.earnings import RATE, EarningsReport, report_for
from app.timeutil import current_month, human_ist

router = RouterSpec("account")
router.message.filter(F.chat.type == ChatType.PRIVATE)


def _require_verified(user) -> str | None:
    if user is None or not user["verified"]:
        return (
            "You are not verified yet. Send /start and tap the button — it "
            "takes one step."
        )
    if user["duplicate"]:
        return "🚫 This account is flagged as a duplicate and cannot earn."
    if user["banned"]:
        return "🚫 This account is blocked."
    return None


def format_earnings(report: EarningsReport, verbose: bool = True) -> str:
    st = report.referrer_status
    lines = [
        f"💰 <b>Earnings — {report.month}</b>",
        "",
        f"Referrals: <b>{report.total_referrals}</b>  "
        f"(active <b>{report.active_referrals}</b>, inactive {report.inactive_referrals})",
        f"Rate: ₹{RATE:g} per active referral",
        f"Amount this month: <b>₹{report.amount:g}</b>",
    ]
    if not report.payable:
        lines += [
            "",
            f"⚠️ You are not eligible right now: <b>{esc(st.reason)}</b>.",
            f"Your referrals are worth ₹{report.gross:g}, but you only get paid "
            "for a month in which you are in both your group and your channel "
            "and interacted with the bot at least once.",
        ]

    if verbose and report.rows:
        lines += ["", "<b>Your referrals</b>"]
        for row in report.rows[:40]:
            mark = "✅" if row.status.active else "❌"
            name = row.user["full_name"] or row.user["username"] or row.user["uid"]
            detail = (
                f"{row.status.interactions} interaction(s)"
                if row.status.active
                else row.status.reason
            )
            lines.append(f"{mark} {esc(name)} — <code>{esc(row.user['uid'])}</code> · {esc(detail)}")
        if len(report.rows) > 40:
            lines.append(f"… and {len(report.rows) - 40} more")
    elif verbose:
        lines += ["", "You have no referrals yet. Send /link to get your link."]
    return "\n".join(lines)


@router.message(Command("earnings"))
async def cmd_earnings(message: Message) -> None:
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    problem = _require_verified(user)
    if problem:
        await message.answer(problem, reply_markup=contact_keyboard())
        return
    await message.answer(format_earnings(report_for(user)))


@router.callback_query(F.data == "menu:earnings")
async def cb_earnings(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = db.get_user(callback.from_user.id)
    problem = _require_verified(user)
    if problem:
        await callback.message.answer(problem)
        return
    await callback.message.answer(format_earnings(report_for(user)))


@router.callback_query(F.data == "menu:referrals")
async def cb_referrals(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = db.get_user(callback.from_user.id)
    problem = _require_verified(user)
    if problem:
        await callback.message.answer(problem)
        return
    report = report_for(user)
    if not report.rows:
        await callback.message.answer("You have no referrals yet. Send /link to get your link.")
        return
    lines = [f"👥 <b>Your referrals ({report.total_referrals})</b>", ""]
    for row in report.rows[:60]:
        mark = "✅" if row.status.active else "❌"
        name = row.user["full_name"] or row.user["username"] or row.user["uid"]
        lines.append(
            f"{mark} {esc(name)} · <code>{esc(row.user['uid'])}</code> · "
            f"joined {esc(human_ist(row.user['joined_at']))}"
        )
    if len(report.rows) > 60:
        lines.append(f"… and {len(report.rows) - 60} more")
    await callback.message.answer("\n".join(lines))


async def _do_withdraw(user, answer) -> None:
    month = current_month()
    report = report_for(user, month)
    user_id = int(user["id"])

    if not report.payable:
        await answer(
            "❌ You cannot request a payout for this month yet.\n\n"
            f"Reason: <b>{esc(report.referrer_status.reason)}</b>\n\n"
            "Be a member of both your group and your channel, and interact with "
            "the bot at least once this month."
        )
        return
    if report.amount <= 0:
        await answer(
            "You have no active referrals this month, so there is nothing to "
            "withdraw yet. Send /link and invite someone."
        )
        return

    bank = db.get_bank_details(user_id)
    if bank is None:
        await answer(
            "🏦 Before requesting a payout, send /bank once so we know where to "
            "transfer the money."
        )
        return

    existing = db.get_withdrawal(user_id, month)
    if existing is not None:
        await answer(
            f"You already have a <b>{esc(existing['status'])}</b> request for "
            f"{esc(month)} of ₹{existing['amount']:g}. Requests are processed "
            "manually after the month ends."
        )
        return

    row = db.create_withdrawal(user_id, month, report.amount)
    if row is None:
        await answer("A request for this month already exists.")
        return

    db.log_event("withdraw_requested", user_id, f"{month} ₹{report.amount:g}")
    await answer(
        f"✅ <b>Payout requested</b>\n\n"
        f"Month: {esc(month)}\n"
        f"Active referrals: {report.active_referrals}\n"
        f"Amount: <b>₹{report.amount:g}</b>\n"
        f"To: {esc(bank['full_name'])} · {esc(mask_account(bank['account_number']))} · "
        f"{esc(bank['ifsc'])}\n\n"
        "An admin reviews requests and transfers after the month closes. You "
        "will get a message when it is marked paid."
    )
    await notify_admins(
        f"💸 Payout request from {esc(user['uid'])} — ₹{report.amount:g} for {esc(month)} "
        f"({report.active_referrals} active referrals)."
    )


@router.message(Command("withdraw"))
async def cmd_withdraw(message: Message) -> None:
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    problem = _require_verified(user)
    if problem:
        await message.answer(problem, reply_markup=contact_keyboard())
        return
    await _do_withdraw(user, message.answer)


@router.callback_query(F.data == "menu:withdraw")
async def cb_withdraw(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = db.get_user(callback.from_user.id)
    problem = _require_verified(user)
    if problem:
        await callback.message.answer(problem)
        return
    await _do_withdraw(user, callback.message.answer)


@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot) -> None:
    """Plain-language answer to 'am I counted this month?'."""
    if message.from_user is None:
        return
    user = db.get_user(message.from_user.id)
    problem = _require_verified(user)
    if problem:
        await message.answer(problem, reply_markup=contact_keyboard())
        return
    report = report_for(user)
    st = report.referrer_status
    await message.answer(
        f"📊 <b>Status — {esc(st.month)}</b>\n\n"
        f"In your group: {'✅' if st.in_group else '❌'}\n"
        f"In your channel: {'✅' if st.in_channel else '❌'}\n"
        f"Interactions this month: <b>{st.interactions}</b>\n"
        f"Counted as active: {'✅ yes' if st.active else '❌ no — ' + esc(st.reason)}"
    )

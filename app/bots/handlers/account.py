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
from app.earnings import EarningsReport, report_for
from app.timeutil import current_month, human_ist

router = RouterSpec("account")
router.message.filter(F.chat.type == ChatType.PRIVATE)


def _require_verified(user) -> str | None:
    if user is None or not db.has_flag(user, db.F_VERIFIED):
        return (
            "You are not verified yet. Send /start and tap the button — it "
            "takes one step."
        )
    if db.has_flag(user, db.F_DUPLICATE):
        return "🚫 This account is flagged as a duplicate and cannot earn."
    if db.has_flag(user, db.F_BANNED):
        return "🚫 This account is blocked."
    return None


def _breakdown_lines(rows, limit: int) -> list[str]:
    out: list[str] = []
    for row in rows[:limit]:
        mark = "✅" if row.status.active else "❌"
        detail = (
            f"active · ₹{row.amount:g}"
            if row.status.active
            else row.status.reason
        )
        via = f" · via {esc(row.via_uid)}" if row.via_uid else ""
        out.append(f"{mark} <code>{esc(row.user['uid'])}</code> · {esc(detail)}{via}")
    if len(rows) > limit:
        out.append(f"… and {len(rows) - limit} more")
    return out


def format_earnings(report: EarningsReport, verbose: bool = True) -> str:
    st = report.referrer_status
    rates = report.rates
    lines = [
        f"💰 <b>Earnings — {report.month}</b>",
        "",
        f"🥇 <b>Level 1</b> (people you invited): {report.total_referrals} "
        f"— active <b>{report.active_referrals}</b> × ₹{rates.level1:g} = "
        f"<b>₹{report.level1_amount:g}</b>",
        f"🥈 <b>Level 2</b> (people <i>they</i> invited): {report.total_indirect} "
        f"— active <b>{report.active_indirect}</b> × ₹{rates.level2:g} = "
        f"<b>₹{report.level2_amount:g}</b>",
        "",
        f"💵 Total this month: <b>₹{report.amount:g}</b>",
    ]
    if not report.payable:
        lines += [
            "",
            f"⚠️ You are not eligible right now: <b>{esc(st.reason)}</b>.",
            f"Your downline is worth ₹{report.gross:g}, but you only get paid "
            "for a month in which you are in both your group and your channel "
            "and interacted with the bot at least once.",
        ]

    if verbose and report.level1_rows:
        lines += ["", f"<b>Level 1 — ₹{rates.level1:g} each</b>"]
        lines += _breakdown_lines(report.level1_rows, 25)
    if verbose and report.level2_rows:
        lines += ["", f"<b>Level 2 — ₹{rates.level2:g} each</b>"]
        lines += _breakdown_lines(report.level2_rows, 25)
    if verbose and not report.rows:
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

    lines = [
        f"👥 <b>Your downline</b> — {report.total_referrals} direct, "
        f"{report.total_indirect} indirect",
    ]
    for title, rows in (
        ("🥇 Level 1 — you invited them", report.level1_rows),
        ("🥈 Level 2 — your referrals invited them", report.level2_rows),
    ):
        if not rows:
            continue
        lines += ["", f"<b>{title}</b>"]
        for row in rows[:40]:
            mark = "✅" if row.status.active else "❌"
            via = f" · via {esc(row.via_uid)}" if row.via_uid else ""
            lines.append(
                f"{mark} <code>{esc(row.user['uid'])}</code> · "
                f"joined {esc(human_ist(row.user['joined_at']))}{via}"
            )
        if len(rows) > 40:
            lines.append(f"… and {len(rows) - 40} more")
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
            "Nobody in your downline is active this month, so there is nothing "
            "to withdraw yet. Send /link and invite someone."
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
        f"Level 1: {report.active_referrals} active × ₹{report.rates.level1:g} = "
        f"₹{report.level1_amount:g}\n"
        f"Level 2: {report.active_indirect} active × ₹{report.rates.level2:g} = "
        f"₹{report.level2_amount:g}\n"
        f"Amount: <b>₹{report.amount:g}</b>\n"
        f"To: {esc(bank['full_name'])} · {esc(mask_account(bank['account_number']))} · "
        f"{esc(bank['ifsc'])}\n\n"
        "An admin reviews requests and transfers after the month closes. You "
        "will get a message when it is marked paid."
    )
    await notify_admins(
        f"💸 Payout request from {esc(user['uid'])} — ₹{report.amount:g} for {esc(month)} "
        f"({report.active_referrals} active at level 1, "
        f"{report.active_indirect} at level 2)."
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
        f"Interacted this month: {'✅ yes' if st.has_interaction else '❌ not yet'}\n"
        f"Counted as active: {'✅ yes' if st.active else '❌ no — ' + esc(st.reason)}"
    )

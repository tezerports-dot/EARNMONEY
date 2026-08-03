"""Main bot: the one-time /bank conversation.

Four questions, one at a time, each validated before moving on. A user may
submit exactly once — the answers feed the admin's bank-upload export, so a
second attempt is politely refused rather than overwriting anything.
"""

from __future__ import annotations

from aiogram import F
from aiogram.enums import ChatType
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app import db
from app.bots.routerspec import RouterSpec
from app.bank import (
    clean_account_number,
    clean_ifsc,
    clean_name,
    clean_upi,
    mask_account,
)
from app.bots.telegram_utils import esc
from app.timeutil import human_ist

router = RouterSpec("bank")
router.message.filter(F.chat.type == ChatType.PRIVATE)


class BankForm(StatesGroup):
    full_name = State()
    account_number = State()
    ifsc = State()
    upi_id = State()


PROMPTS = {
    BankForm.full_name: (
        "🏦 <b>Bank details (1 of 4)</b>\n\n"
        "Send your <b>full name exactly as printed on the bank account</b>.\n\n"
        "Send /cancel to stop."
    ),
    BankForm.account_number: (
        "🏦 <b>Bank details (2 of 4)</b>\n\n"
        "Send your <b>account number</b> (9–18 digits, no spaces)."
    ),
    BankForm.ifsc: (
        "🏦 <b>Bank details (3 of 4)</b>\n\n"
        "Send your <b>IFSC code</b> (11 characters, e.g. <code>HDFC0001234</code>)."
    ),
    BankForm.upi_id: (
        "🏦 <b>Bank details (4 of 4)</b>\n\n"
        "Send your <b>UPI id</b> (e.g. <code>rahul@okhdfcbank</code>)."
    ),
}


async def _start_form(user_id: int, answer, state: FSMContext) -> None:
    user = db.get_user(user_id)
    if user is None or not user["verified"]:
        await answer("Verify first: send /start and tap the button.")
        return

    existing = db.get_bank_details(int(user["id"]))
    if existing is not None:
        await answer(
            "🔒 <b>Bank details already submitted</b>\n\n"
            f"Name: {esc(existing['full_name'])}\n"
            f"Account: <code>{esc(mask_account(existing['account_number']))}</code>\n"
            f"IFSC: <code>{esc(existing['ifsc'])}</code>\n"
            f"UPI: <code>{esc(existing['upi_id'])}</code>\n"
            f"Submitted: {esc(human_ist(existing['submitted_at']))}\n\n"
            "These can only be submitted once. If something is wrong, contact "
            "an admin — they can correct it for you."
        )
        return

    await state.set_state(BankForm.full_name)
    await answer(PROMPTS[BankForm.full_name])


@router.message(Command("bank"))
async def cmd_bank(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await _start_form(int(message.from_user.id), message.answer, state)


@router.callback_query(F.data == "menu:bank")
async def cb_bank(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    await _start_form(int(callback.from_user.id), callback.message.answer, state)


@router.message(Command("cancel"), StateFilter(BankForm))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled. Nothing was saved. Send /bank to start again.")


@router.message(BankForm.full_name)
async def step_name(message: Message, state: FSMContext) -> None:
    value, error = clean_name(message.text or "")
    if value is None:
        await message.answer(f"❌ {error}\n\nTry again, or /cancel.")
        return
    await state.update_data(full_name=value)
    await state.set_state(BankForm.account_number)
    await message.answer(PROMPTS[BankForm.account_number])


@router.message(BankForm.account_number)
async def step_account(message: Message, state: FSMContext) -> None:
    value, error = clean_account_number(message.text or "")
    if value is None:
        await message.answer(f"❌ {error}\n\nTry again, or /cancel.")
        return
    await state.update_data(account_number=value)
    await state.set_state(BankForm.ifsc)
    await message.answer(PROMPTS[BankForm.ifsc])


@router.message(BankForm.ifsc)
async def step_ifsc(message: Message, state: FSMContext) -> None:
    value, error = clean_ifsc(message.text or "")
    if value is None:
        await message.answer(f"❌ {error}\n\nTry again, or /cancel.")
        return
    await state.update_data(ifsc=value)
    await state.set_state(BankForm.upi_id)
    await message.answer(PROMPTS[BankForm.upi_id])


@router.message(BankForm.upi_id)
async def step_upi(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    value, error = clean_upi(message.text or "")
    if value is None:
        await message.answer(f"❌ {error}\n\nTry again, or /cancel.")
        return

    data = await state.get_data()
    await state.clear()
    user_id = int(message.from_user.id)

    saved = db.save_bank_details(
        user_id=user_id,
        full_name=str(data["full_name"]),
        account_number=str(data["account_number"]),
        ifsc=str(data["ifsc"]),
        upi_id=value,
    )
    if not saved:
        await message.answer(
            "🔒 Bank details were already on file, so nothing was changed."
        )
        return

    db.log_event("bank_details_submitted", user_id, data["ifsc"])
    await message.answer(
        "✅ <b>Saved</b>\n\n"
        f"Name: {esc(data['full_name'])}\n"
        f"Account: <code>{esc(mask_account(str(data['account_number'])))}</code>\n"
        f"IFSC: <code>{esc(data['ifsc'])}</code>\n"
        f"UPI: <code>{esc(value)}</code>\n\n"
        "This is stored once and cannot be changed from the bot. Send "
        "/withdraw when you want this month's payout."
    )

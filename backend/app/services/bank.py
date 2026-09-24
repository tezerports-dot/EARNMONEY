"""Bank details: encrypted at rest, masked everywhere, never logged."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.models import BankAccount, User, WithdrawalRequest
from app.security import crypto
from app.services import audit, risk

NAME = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,99}$")
ACCOUNT_NUMBER = re.compile(r"^[0-9]{9,18}$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def purpose(user_id: int) -> str:
    return f"bank:{user_id}"


def masked(last4: str) -> str:
    return f"XXXX XXXX {last4}"


def validate(name: str, number: str, ifsc: str) -> tuple[str, str, str]:
    name = " ".join((name or "").split())
    number = re.sub(r"\s", "", number or "")
    ifsc = (ifsc or "").strip().upper()
    fields: dict[str, str] = {}
    if not NAME.fullmatch(name):
        fields["account_holder_name"] = "Enter the name as it appears on the bank account."
    if not ACCOUNT_NUMBER.fullmatch(number):
        fields["account_number"] = "Enter 9 to 18 digits."
    if not IFSC.fullmatch(ifsc):
        fields["ifsc"] = "IFSC has 11 characters, like HDFC0001234."
    if fields:
        raise errors.ValidationFailed(fields=fields)
    return name, number, ifsc


async def active_withdrawal(db: AsyncSession, user_id: int) -> WithdrawalRequest | None:
    return (
        await db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.user_id == user_id, WithdrawalRequest.status.in_(("REQUESTED", "PROCESSING"))
            )
        )
    ).scalar_one_or_none()


async def details_json(db: AsyncSession, user: User) -> dict:
    account = await db.get(BankAccount, user.id)
    if account is None:
        return {"status": "NONE"}
    return {
        "status": "SAVED",
        "account_holder_name": account.account_holder_name,
        "account_number_masked": masked(account.account_number_last4),
        "ifsc": account.ifsc,
        "updated_at": timeutil.iso(account.updated_at),
        "locked": await active_withdrawal(db, user.id) is not None,
    }


async def save(db: AsyncSession, user: User, name: str, number: str, ifsc: str) -> dict:
    name, number, ifsc = validate(name, number, ifsc)
    if await active_withdrawal(db, user.id) is not None:
        raise errors.BankDetailsLocked()
    fingerprint = crypto.fingerprint(number, "bank")
    account = (
        await db.execute(select(BankAccount).where(BankAccount.user_id == user.id).with_for_update())
    ).scalar_one_or_none()
    if account is None:
        account = BankAccount(user_id=user.id)
        db.add(account)
    account.account_holder_name = name
    account.account_number_ciphertext = crypto.encrypt(number, purpose(user.id))
    account.account_number_last4 = number[-4:]
    account.account_number_fingerprint = fingerprint
    account.ifsc = ifsc
    account.updated_at = timeutil.now()
    await db.flush()
    await risk.after_bank_details(db, user, fingerprint)
    await audit.record(
        db, f"user:{user.public_id}", "bank.saved", f"user:{user.public_id}", {"last4": number[-4:], "ifsc": ifsc}
    )
    return await details_json(db, user)

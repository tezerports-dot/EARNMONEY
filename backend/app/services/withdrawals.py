"""Withdrawals: requested by the user, paid or failed only by an admin.

REQUESTED → PROCESSING (admin exports a batch) → PAID | FAILED
FAILED returns the money to the user's available balance. A user with an open
risk flag stays REQUESTED until an admin looks and resolves the flag.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, ids, timeutil
from app.models import BankAccount, LedgerAccount, PayoutBatch, RiskFlag, User, WithdrawalRequest
from app.services import audit, ledger, wallet
from app.services import campaign as campaign_service


def as_json(w: WithdrawalRequest) -> dict:
    return {
        "id": f"WD-{w.public_id}",
        "amount_paise": w.amount_paise,
        "status": w.status,
        "bank_account_masked": f"XXXX {w.account_number_last4}",
        "requested_at": timeutil.iso(w.requested_at),
        "paid_at": timeutil.iso(w.paid_at),
        "bank_reference": w.bank_reference,
        "failure_reason": w.failure_reason,
    }


async def create(db: AsyncSession, user: User, amount_paise: int) -> dict:
    if not isinstance(amount_paise, int) or isinstance(amount_paise, bool) or amount_paise <= 0:
        raise errors.ValidationFailed(fields={"amount_paise": "Enter a positive amount."})
    campaign = await campaign_service.current_campaign(db)
    if timeutil.now() < campaign.payout_opens_at:
        raise errors.PayoutsNotOpen()
    bank = await db.get(BankAccount, user.id)
    if bank is None:
        raise errors.BankDetailsRequired()
    if amount_paise < campaign.min_withdrawal_paise:
        raise errors.BelowMinimum()

    await wallet.unlock_if_open(db, user)
    available = (
        await db.execute(
            select(LedgerAccount)
            .where(LedgerAccount.kind == "USER_AVAILABLE", LedgerAccount.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if available is None or available.balance_paise < amount_paise:
        raise errors.InsufficientBalance()

    at = timeutil.now()
    request = WithdrawalRequest(
        public_id=ids.new_reference(),
        user_id=user.id,
        amount_paise=amount_paise,
        status="REQUESTED",
        account_holder_name=bank.account_holder_name,
        account_number_ciphertext=bank.account_number_ciphertext,
        account_number_last4=bank.account_number_last4,
        ifsc=bank.ifsc,
        requested_at=at,
        updated_at=at,
    )
    db.add(request)
    try:
        await db.flush()
    except IntegrityError as exc:
        # The partial unique index allows one active withdrawal per user, so
        # two concurrent requests can't both hold money.
        if "one_active" in str(exc.orig):
            raise errors.WithdrawalInProgress() from exc
        raise
    clearing = await ledger.system_account(db, "WITHDRAWAL_CLEARING")
    txn = await ledger.transfer(
        db,
        kind="WITHDRAWAL_HOLD",
        idempotency_key=f"withdrawal:{request.id}:hold",
        source=available,
        destination=clearing,
        amount_paise=amount_paise,
        created_by=f"user:{user.public_id}",
        reference_type="withdrawal",
        reference_id=request.id,
    )
    assert txn is not None
    request.hold_transaction_id = txn.id
    await audit.record(
        db,
        f"user:{user.public_id}",
        "withdrawal.requested",
        f"withdrawal:{request.public_id}",
        {"amount_paise": amount_paise},
    )
    return as_json(request)


async def history(db: AsyncSession, user: User, limit: int, cursor: str | None) -> dict:
    limit = max(1, min(limit, 50))
    query = (
        select(WithdrawalRequest)
        .where(WithdrawalRequest.user_id == user.id)
        .order_by(WithdrawalRequest.requested_at.desc(), WithdrawalRequest.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            at_raw, row_id = json.loads(base64.urlsafe_b64decode(padded))
            at = datetime.fromisoformat(at_raw)
        except (ValueError, TypeError) as exc:
            raise errors.ValidationFailed(fields={"cursor": "Invalid cursor."}) from exc
        query = query.where(
            or_(
                WithdrawalRequest.requested_at < at,
                and_(WithdrawalRequest.requested_at == at, WithdrawalRequest.id < row_id),
            )
        )
    rows = list((await db.execute(query)).scalars())
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        raw = json.dumps([last.requested_at.isoformat(), last.id]).encode()
        next_cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return {"items": [as_json(w) for w in rows[:limit]], "next_cursor": next_cursor}


# --- Admin side ------------------------------------------------------------


async def create_batch(db: AsyncSession, admin: str, limit: int = 1000) -> PayoutBatch | None:
    """Batch the oldest requests, holding back anyone with an open risk flag."""
    flagged = select(RiskFlag.user_id).where(RiskFlag.resolved_at.is_(None))
    requests = list(
        (
            await db.execute(
                select(WithdrawalRequest)
                .where(WithdrawalRequest.status == "REQUESTED", WithdrawalRequest.user_id.not_in(flagged))
                .order_by(WithdrawalRequest.requested_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    if not requests:
        return None
    batch = PayoutBatch(created_by=admin, request_count=len(requests), total_paise=sum(r.amount_paise for r in requests))
    db.add(batch)
    await db.flush()
    at = timeutil.now()
    for r in requests:
        r.status, r.processing_at, r.batch_id, r.updated_at = "PROCESSING", at, batch.id, at
    await audit.record(
        db, admin, "payout.batch_created", f"batch:{batch.id}", {"count": len(requests), "total_paise": batch.total_paise}
    )
    return batch


async def _locked(db: AsyncSession, public_id: str) -> WithdrawalRequest:
    request = (
        await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.public_id == public_id).with_for_update())
    ).scalar_one_or_none()
    if request is None:
        raise errors.NotFound()
    return request


async def mark_paid(db: AsyncSession, admin: str, public_id: str, bank_reference: str) -> WithdrawalRequest:
    request = await _locked(db, public_id)
    if request.status != "PROCESSING":
        raise errors.ValidationFailed(f"Only processing withdrawals can be marked paid (this one is {request.status}).")
    reference = bank_reference.strip()[:64]
    if not reference:
        raise errors.ValidationFailed(fields={"bank_reference": "Enter the bank reference (UTR)."})
    txn = await ledger.transfer(
        db,
        kind="WITHDRAWAL_PAID",
        idempotency_key=f"withdrawal:{request.id}:settle",
        source=await ledger.system_account(db, "WITHDRAWAL_CLEARING"),
        destination=await ledger.system_account(db, "PAYOUT_SETTLED"),
        amount_paise=request.amount_paise,
        created_by=admin,
        reference_type="withdrawal",
        reference_id=request.id,
    )
    at = timeutil.now()
    request.status, request.paid_at, request.bank_reference, request.updated_at = "PAID", at, reference, at
    request.settle_transaction_id = txn.id if txn else request.settle_transaction_id
    await audit.record(db, admin, "withdrawal.paid", f"withdrawal:{request.public_id}", {"reference": reference})
    return request


async def mark_failed(db: AsyncSession, admin: str, public_id: str, reason: str) -> WithdrawalRequest:
    request = await _locked(db, public_id)
    if request.status not in ("REQUESTED", "PROCESSING"):
        raise errors.ValidationFailed(f"This withdrawal is already {request.status}.")
    reason = reason.strip()[:200] or "The bank could not complete the payment."
    available = await ledger.user_account(db, "USER_AVAILABLE", request.user_id)
    txn = await ledger.transfer(
        db,
        kind="WITHDRAWAL_RETURNED",
        idempotency_key=f"withdrawal:{request.id}:settle",
        source=await ledger.system_account(db, "WITHDRAWAL_CLEARING"),
        destination=available,
        amount_paise=request.amount_paise,
        created_by=admin,
        reference_type="withdrawal",
        reference_id=request.id,
    )
    at = timeutil.now()
    request.status, request.failed_at, request.failure_reason, request.updated_at = "FAILED", at, reason, at
    request.settle_transaction_id = txn.id if txn else request.settle_transaction_id
    await audit.record(db, admin, "withdrawal.failed", f"withdrawal:{request.public_id}", {"reason": reason})
    return request

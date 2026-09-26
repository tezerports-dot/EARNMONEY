"""Wallet figures, all read from the ledger."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import (
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    ReferralReward,
    User,
    WithdrawalRequest,
)
from app.models.ledger import USER_ACCOUNT_KINDS
from app.services import campaign as campaign_service
from app.services import ledger

USER_ENTRY_KINDS = {
    "REFERRAL_REWARD": "REFERRAL_REWARD",
    "REWARDS_UNLOCK": "REWARDS_UNLOCKED",
    "WITHDRAWAL_HOLD": "WITHDRAWAL",
    "WITHDRAWAL_RETURNED": "WITHDRAWAL_RETURNED",
}


async def unlock_if_open(db: AsyncSession, user: User) -> int:
    """On or after the payout date, move the pending balance to available.

    Runs whenever the wallet is read or a withdrawal is made, and in a batch
    job on the payout date. The pending account is locked, so concurrent
    calls serialize and only the first one moves anything.
    """
    campaign = await campaign_service.current_campaign(db)
    if timeutil.now() < campaign.payout_opens_at:
        return 0
    pending = (
        await db.execute(
            select(LedgerAccount).where(LedgerAccount.kind == "USER_PENDING", LedgerAccount.user_id == user.id).with_for_update()
        )
    ).scalar_one_or_none()
    if pending is None or pending.balance_paise <= 0:
        return 0
    amount = pending.balance_paise
    last_entry = (await db.execute(select(func.max(LedgerEntry.id)).where(LedgerEntry.account_id == pending.id))).scalar_one()
    available = await ledger.user_account(db, "USER_AVAILABLE", user.id)
    await ledger.transfer(
        db,
        kind="REWARDS_UNLOCK",
        idempotency_key=f"unlock:{user.id}:{last_entry}",
        source=pending,
        destination=available,
        amount_paise=amount,
        created_by="system",
        reference_type="user",
        reference_id=user.id,
    )
    return amount


async def _sum_withdrawals(db: AsyncSession, user_id: int, statuses: tuple[str, ...]) -> int:
    return int(
        (
            await db.execute(
                select(func.coalesce(func.sum(WithdrawalRequest.amount_paise), 0)).where(
                    WithdrawalRequest.user_id == user_id, WithdrawalRequest.status.in_(statuses)
                )
            )
        ).scalar_one()
    )


async def entries(db: AsyncSession, user_id: int, limit: int, before_id: int | None = None) -> list[dict]:
    """The user's side of each ledger transaction, newest first."""
    query = (
        select(LedgerEntry, LedgerTransaction, LedgerAccount.kind)
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        # Naming the kinds (the only ones a user can own) lets Postgres use the
        # (kind, user_id) index instead of scanning every account.
        .where(LedgerAccount.kind.in_(USER_ACCOUNT_KINDS), LedgerAccount.user_id == user_id)
        .order_by(LedgerEntry.id.desc())
        .limit(limit * 2 + 2)
    )
    if before_id is not None:
        query = query.where(LedgerEntry.id < before_id)
    rows = (await db.execute(query)).all()

    reward_sources: dict[int, str] = {}
    source_ids = [txn.reference_id for _, txn, _ in rows if txn.kind == "REFERRAL_REWARD" and txn.reference_id]
    if source_ids:
        reward_sources = dict((await db.execute(select(User.id, User.public_id).where(User.id.in_(source_ids)))).all())

    items: list[dict] = []
    seen: set[int] = set()
    for entry, txn, account_kind in rows:
        kind = USER_ENTRY_KINDS.get(txn.kind)
        if kind is None or txn.id in seen:
            continue
        # An unlock touches two of the user's accounts; show it once, as the
        # credit to available.
        if txn.kind == "REWARDS_UNLOCK" and account_kind != "USER_AVAILABLE":
            continue
        seen.add(txn.id)
        items.append(
            {
                "id": f"TX-{txn.public_id}",
                "kind": kind,
                "direction": "CREDIT" if entry.amount_paise > 0 else "DEBIT",
                "amount_paise": abs(entry.amount_paise),
                "created_at": timeutil.iso(txn.created_at),
                "counterparty_public_id": reward_sources.get(txn.reference_id or -1) if txn.kind == "REFERRAL_REWARD" else None,
                "_cursor": entry.id,
            }
        )
        if len(items) == limit:
            break
    return items


async def summary(db: AsyncSession, user: User) -> dict:
    await unlock_if_open(db, user)
    campaign = await campaign_service.current_campaign(db)
    reward_count, reward_total = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(ReferralReward.amount_paise), 0)).where(
                ReferralReward.beneficiary_id == user.id, ReferralReward.status == "CREDITED"
            )
        )
    ).one()
    recent = await entries(db, user.id, 10)
    for item in recent:
        item.pop("_cursor")
    return {
        "total_earned_paise": int(reward_total),
        "pending_paise": await ledger.balance(db, "USER_PENDING", user.id),
        "available_paise": await ledger.balance(db, "USER_AVAILABLE", user.id),
        "in_withdrawal_paise": await _sum_withdrawals(db, user.id, ("REQUESTED", "PROCESSING")),
        "withdrawn_paise": await _sum_withdrawals(db, user.id, ("PAID",)),
        "payouts_open": timeutil.now() >= campaign.payout_opens_at,
        "payout_opens_at": timeutil.iso(campaign.payout_opens_at),
        "min_withdrawal_paise": campaign.min_withdrawal_paise,
        "breakdown": [{"level": 1, "reward_count": int(reward_count), "amount_paise": int(reward_total)}],
        "recent_entries": recent,
    }


async def entries_page(db: AsyncSession, user: User, limit: int, cursor: str | None) -> dict:
    limit = max(1, min(limit, 50))
    before = None
    if cursor:
        try:
            before = int(cursor)
        except ValueError:
            before = None
    items = await entries(db, user.id, limit + 1, before)
    next_cursor = str(items[limit - 1]["_cursor"]) if len(items) > limit else None
    items = items[:limit]
    for item in items:
        item.pop("_cursor")
    return {"items": items, "next_cursor": next_cursor}

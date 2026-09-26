"""Double-entry ledger. The only code that changes a balance.

Every posting is one ``ledger_transactions`` row plus entries that sum to
zero. Balances are cached on ``ledger_accounts`` and updated in the same
transaction under row locks. The database rejects negative user balances and
unbalanced transactions (see the initial migration), so a bug here fails
loudly instead of creating money.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, ids
from app.models import LedgerAccount, LedgerEntry, LedgerTransaction


@dataclass(frozen=True)
class Posting:
    account_id: int
    amount_paise: int


async def system_account(db: AsyncSession, kind: str) -> LedgerAccount:
    return (
        await db.execute(select(LedgerAccount).where(LedgerAccount.kind == kind, LedgerAccount.user_id.is_(None)))
    ).scalar_one()


async def user_account(db: AsyncSession, kind: str, user_id: int) -> LedgerAccount:
    await db.execute(
        insert(LedgerAccount)
        .values(kind=kind, user_id=user_id)
        .on_conflict_do_nothing(index_elements=["kind", "user_id"], index_where=LedgerAccount.user_id.is_not(None))
    )
    return (
        await db.execute(select(LedgerAccount).where(LedgerAccount.kind == kind, LedgerAccount.user_id == user_id))
    ).scalar_one()


async def balance(db: AsyncSession, kind: str, user_id: int, *, lock: bool = False) -> int:
    query = select(LedgerAccount.balance_paise).where(LedgerAccount.kind == kind, LedgerAccount.user_id == user_id)
    if lock:
        query = query.with_for_update()
    value = (await db.execute(query)).scalar_one_or_none()
    return int(value or 0)


async def post(
    db: AsyncSession,
    *,
    kind: str,
    idempotency_key: str,
    postings: list[Posting],
    created_by: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
    memo: str | None = None,
) -> LedgerTransaction | None:
    """Post a balanced transaction once.

    Returns the new transaction, or ``None`` if ``idempotency_key`` was
    already posted (the retry changes nothing). Raises
    ``InsufficientBalance`` if an account would go below zero.
    """
    if not postings or sum(p.amount_paise for p in postings) != 0:
        raise ValueError("postings must be non-empty and sum to zero")
    if any(not isinstance(p.amount_paise, int) or p.amount_paise == 0 for p in postings):
        raise ValueError("amounts must be non-zero integer paise")

    created = await db.execute(
        insert(LedgerTransaction)
        .values(
            public_id=ids.new_reference(),
            kind=kind,
            idempotency_key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=created_by,
            memo=memo,
        )
        .on_conflict_do_nothing(index_elements=[LedgerTransaction.idempotency_key])
        .returning(LedgerTransaction.id)
    )
    txn_id = created.scalar_one_or_none()
    if txn_id is None:
        return None

    # Lock accounts in id order so concurrent postings can't deadlock.
    for posting in sorted(postings, key=lambda p: p.account_id):
        try:
            await db.execute(
                update(LedgerAccount)
                .where(LedgerAccount.id == posting.account_id)
                .values(balance_paise=LedgerAccount.balance_paise + posting.amount_paise)
            )
        except IntegrityError as exc:
            # The caller's transaction is now aborted and rolls back entirely.
            if "no_negative_balance" in str(exc.orig):
                raise errors.InsufficientBalance() from exc
            raise
    db.add_all(LedgerEntry(transaction_id=txn_id, account_id=p.account_id, amount_paise=p.amount_paise) for p in postings)
    await db.flush()
    return (await db.execute(select(LedgerTransaction).where(LedgerTransaction.id == txn_id))).scalar_one()


async def transfer(
    db: AsyncSession,
    *,
    kind: str,
    idempotency_key: str,
    source: LedgerAccount,
    destination: LedgerAccount,
    amount_paise: int,
    created_by: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
    memo: str | None = None,
) -> LedgerTransaction | None:
    if amount_paise <= 0:
        raise ValueError("amount must be positive")
    return await post(
        db,
        kind=kind,
        idempotency_key=idempotency_key,
        postings=[Posting(source.id, -amount_paise), Posting(destination.id, amount_paise)],
        created_by=created_by,
        reference_type=reference_type,
        reference_id=reference_id,
        memo=memo,
    )

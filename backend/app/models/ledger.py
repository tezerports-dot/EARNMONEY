from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, one_of, pk, timestamp_column

ACCOUNT_KINDS = (
    "COMPANY_FUNDING",
    "PROMO_POOL",
    "USER_PENDING",
    "USER_AVAILABLE",
    "WITHDRAWAL_CLEARING",
    "PAYOUT_SETTLED",
)
USER_ACCOUNT_KINDS = ("USER_PENDING", "USER_AVAILABLE")

TRANSACTION_KINDS = (
    "FUNDING",
    "REFERRAL_REWARD",
    "REWARDS_UNLOCK",
    "WITHDRAWAL_HOLD",
    "WITHDRAWAL_PAID",
    "WITHDRAWAL_RETURNED",
    "ADJUSTMENT",
)


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(one_of("kind", ACCOUNT_KINDS), name="kind"),
        CheckConstraint(
            f"({one_of('kind', USER_ACCOUNT_KINDS)}) = (user_id IS NOT NULL)",
            name="user_accounts_have_owner",
        ),
        # Only the external funding source may go negative.
        CheckConstraint("kind = 'COMPANY_FUNDING' OR balance_paise >= 0", name="no_negative_balance"),
        Index("uq_ledger_accounts_user_kind", "kind", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL")),
        Index("uq_ledger_accounts_system_kind", "kind", unique=True, postgresql_where=text("user_id IS NULL")),
    )

    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    balance_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = timestamp_column()


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    __table_args__ = (CheckConstraint(one_of("kind", TRANSACTION_KINDS), name="kind"),)

    id: Mapped[int] = pk()
    public_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp_column()


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_paise <> 0", name="amount_non_zero"),
        Index("ix_ledger_entries_account_recent", "account_id", text("id DESC")),
        Index("ix_ledger_entries_transaction", "transaction_id"),
    )

    id: Mapped[int] = pk()
    transaction_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ledger_transactions.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ledger_accounts.id"), nullable=False)
    # Signed: the account's new balance is its old balance plus this amount.
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        CheckConstraint("ifsc ~ '^[A-Z]{4}0[A-Z0-9]{6}$'", name="ifsc_format"),
        CheckConstraint("account_number_last4 ~ '^[0-9]{4}$'", name="last4_format"),
        Index("ix_bank_accounts_fingerprint", "account_number_fingerprint"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    account_holder_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    account_number_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ifsc: Mapped[str] = mapped_column(String(11), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()


WITHDRAWAL_STATUSES = ("REQUESTED", "PROCESSING", "PAID", "FAILED")


class PayoutBatch(Base):
    __tablename__ = "payout_batches"

    id: Mapped[int] = pk()
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    request_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        CheckConstraint(one_of("status", WITHDRAWAL_STATUSES), name="status"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        Index(
            "uq_withdrawal_requests_one_active",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('REQUESTED', 'PROCESSING')"),
        ),
        Index("ix_withdrawal_requests_status", "status", "requested_at"),
        Index("ix_withdrawal_requests_user_recent", "user_id", text("requested_at DESC")),
    )

    id: Mapped[int] = pk()
    public_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="REQUESTED")
    # Copied from bank_accounts when requested, so a later edit can't redirect it.
    account_holder_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    ifsc: Mapped[str] = mapped_column(String(11), nullable=False)
    hold_transaction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ledger_transactions.id"))
    settle_transaction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ledger_transactions.id"))
    batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payout_batches.id"))
    bank_reference: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = timestamp_column()

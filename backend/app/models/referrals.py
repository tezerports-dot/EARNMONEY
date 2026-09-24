from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, one_of, pk, timestamp_column

# Levels that are tracked. Only level 1 is ever paid (see ReferralReward).
MAX_TRACKED_LEVEL = 4
PAID_LEVEL = 1


class ReferralEdge(Base):
    """Closure table: one row per (ancestor, descendant) up to four levels apart."""

    __tablename__ = "referral_edges"
    __table_args__ = (
        PrimaryKeyConstraint("descendant_id", "level", name="pk_referral_edges"),
        UniqueConstraint("ancestor_id", "descendant_id"),
        CheckConstraint(f"level BETWEEN 1 AND {MAX_TRACKED_LEVEL}", name="level_range"),
        CheckConstraint(one_of("status", ("PENDING", "QUALIFIED")), name="status"),
        CheckConstraint("ancestor_id <> descendant_id", name="no_self_edge"),
        Index("ix_referral_edges_counting", "ancestor_id", "level", postgresql_where=text("status = 'QUALIFIED'")),
    )

    ancestor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    descendant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    created_at: Mapped[datetime] = timestamp_column()
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("source_user_id", "level"),
        # The agreed rule: only direct referrals pay. Deeper levels can never
        # produce a reward row, whatever the application code does.
        CheckConstraint(f"level = {PAID_LEVEL}", name="only_level_one_pays"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        CheckConstraint("beneficiary_id <> source_user_id", name="no_self_reward"),
        CheckConstraint(one_of("status", ("CREDITED", "REVERSED")), name="status"),
        Index("ix_referral_rewards_beneficiary", "beneficiary_id", "created_at"),
    )

    id: Mapped[int] = pk()
    beneficiary_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    source_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campaign_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaigns.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="CREDITED")
    ledger_transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ledger_transactions.id"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = timestamp_column()


class ReferralSnapshot(Base):
    """Latest daily snapshot per user. Income for levels 2–4 is always zero."""

    __tablename__ = "referral_snapshots"
    __table_args__ = (
        CheckConstraint(
            "level_1_count >= 0 AND level_2_count >= 0 AND level_3_count >= 0 AND level_4_count >= 0",
            name="counts_non_negative",
        ),
        CheckConstraint("level_1_income_paise >= 0", name="level_1_income_non_negative"),
        CheckConstraint("level_2_income_paise = 0", name="level_2_unpaid"),
        CheckConstraint("level_3_income_paise = 0", name="level_3_unpaid"),
        CheckConstraint("level_4_income_paise = 0", name="level_4_unpaid"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    level_1_count: Mapped[int] = mapped_column(Integer, nullable=False)
    level_2_count: Mapped[int] = mapped_column(Integer, nullable=False)
    level_3_count: Mapped[int] = mapped_column(Integer, nullable=False)
    level_4_count: Mapped[int] = mapped_column(Integer, nullable=False)
    level_1_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level_2_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    level_3_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    level_4_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

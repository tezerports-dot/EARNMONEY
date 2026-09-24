"""Fraud signals for admin review. Never shown to users and never automatic
punishment: a flag only asks a person to look before paying out."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import BankAccount, ReferralReward, RiskFlag, User

REFERRAL_BURST_WINDOW = timedelta(hours=1)
REFERRAL_BURST_THRESHOLD = 30


async def flag(db: AsyncSession, user_id: int, kind: str, details: dict | None = None) -> None:
    exists = (
        await db.execute(
            select(RiskFlag.id).where(RiskFlag.user_id == user_id, RiskFlag.kind == kind, RiskFlag.resolved_at.is_(None))
        )
    ).first()
    if exists is None:
        db.add(RiskFlag(user_id=user_id, kind=kind, details=details or {}))


async def after_verification(db: AsyncSession, user: User) -> None:
    """A referrer whose friends verify unusually fast gets a look."""
    if user.referrer_id is None:
        return
    since = timeutil.now() - REFERRAL_BURST_WINDOW
    recent = (
        await db.execute(
            select(func.count())
            .select_from(ReferralReward)
            .where(ReferralReward.beneficiary_id == user.referrer_id, ReferralReward.created_at >= since)
        )
    ).scalar_one()
    if recent >= REFERRAL_BURST_THRESHOLD:
        await flag(db, user.referrer_id, "REFERRAL_BURST", {"rewards_last_hour": recent})


async def after_bank_details(db: AsyncSession, user: User, fingerprint: bytes) -> None:
    """One bank account behind many users suggests fake accounts."""
    others = list(
        (
            await db.execute(
                select(BankAccount.user_id).where(
                    BankAccount.account_number_fingerprint == fingerprint, BankAccount.user_id != user.id
                )
            )
        ).scalars()
    )
    if others:
        await flag(db, user.id, "SHARED_BANK_ACCOUNT", {"other_accounts": len(others)})
        for other in others[:20]:
            await flag(db, other, "SHARED_BANK_ACCOUNT", {"other_accounts": len(others)})

"""Referral rewards. Only direct referrals (level 1) are ever paid.

Called inside the verification transaction. A reward is created at most once
per verified user: the ledger idempotency key and the ``UNIQUE
(source_user_id, level)`` constraint both guarantee it, so retries and
duplicate Telegram updates can't pay twice.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import PAID_LEVEL, LedgerAccount, ReferralReward, User
from app.services import audit, ledger
from app.services import campaign as campaign_service


async def credit_for_verified_user(db: AsyncSession, user: User) -> ReferralReward | None:
    if user.referrer_id is None:
        return None
    already = (
        await db.execute(
            select(ReferralReward).where(ReferralReward.source_user_id == user.id, ReferralReward.level == PAID_LEVEL)
        )
    ).scalar_one_or_none()
    if already is not None:
        return already

    referrer = await db.get(User, user.referrer_id)
    target = f"user:{user.public_id}"
    if referrer is None or referrer.status != "ACTIVE":
        await audit.record(db, "system", "reward.skipped", target, {"reason": "referrer_not_active"})
        return None

    campaign = await campaign_service.current_campaign(db)
    amount = campaign.level_1_reward_paise
    if campaign_service.status(campaign) != "ACTIVE":
        await audit.record(db, "system", "reward.skipped", target, {"reason": "campaign_not_active"})
        return None

    # Lock the pool so the budget check and the debit can't race.
    pool = (await db.execute(select(LedgerAccount).where(LedgerAccount.kind == "PROMO_POOL").with_for_update())).scalar_one()
    if pool.balance_paise < amount:
        await audit.record(db, "system", "reward.skipped", target, {"reason": "promotional_pool_empty"})
        return None

    pending = await ledger.user_account(db, "USER_PENDING", referrer.id)
    txn = await ledger.transfer(
        db,
        kind="REFERRAL_REWARD",
        idempotency_key=f"reward:{user.id}:{PAID_LEVEL}",
        source=pool,
        destination=pending,
        amount_paise=amount,
        created_by="system",
        reference_type="user",
        reference_id=user.id,
    )
    if txn is None:
        return None
    reward = ReferralReward(
        beneficiary_id=referrer.id,
        source_user_id=user.id,
        level=PAID_LEVEL,
        amount_paise=amount,
        campaign_id=campaign.id,
        ledger_transaction_id=txn.id,
        created_at=timeutil.now(),  # the app's clock, like every rule that reads it (risk.after_verification)
    )
    db.add(reward)
    await db.flush()
    await audit.record(
        db,
        "system",
        "reward.credited",
        f"user:{referrer.public_id}",
        {"source": user.public_id, "level": PAID_LEVEL, "amount_paise": amount, "transaction": txn.public_id},
    )
    return reward

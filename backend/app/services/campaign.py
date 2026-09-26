"""Campaign state and the public configuration the app reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import AppSettings, Campaign, LedgerAccount, LedgerEntry, LedgerTransaction, MembershipCounter
from app.models.referrals import MAX_TRACKED_LEVEL


async def current_campaign(db: AsyncSession) -> Campaign:
    return (await db.execute(select(Campaign).where(Campaign.is_current))).scalar_one()


async def app_settings(db: AsyncSession) -> AppSettings:
    return (await db.execute(select(AppSettings).where(AppSettings.id == 1))).scalar_one()


def status(campaign: Campaign, at: datetime | None = None) -> str:
    at = at or timeutil.now()
    if at < campaign.starts_at:
        return "NOT_STARTED"
    if at >= campaign.ends_at:
        return "ENDED"
    if campaign.paused:
        return "PAUSED"
    return "ACTIVE"


@dataclass(frozen=True)
class Gates:
    status: str
    signups_open: bool
    rewards_open: bool
    payouts_open: bool


async def verified_count(db: AsyncSession) -> int:
    return (await db.execute(select(MembershipCounter.verified_count))).scalar_one()


async def pool_balance(db: AsyncSession) -> int:
    return (await db.execute(select(LedgerAccount.balance_paise).where(LedgerAccount.kind == "PROMO_POOL"))).scalar_one()


async def gates(db: AsyncSession, campaign: Campaign | None = None) -> Gates:
    campaign = campaign or await current_campaign(db)
    at = timeutil.now()
    state = status(campaign, at)
    members = await verified_count(db)
    pool = await pool_balance(db)
    return Gates(
        status=state,
        signups_open=state == "ACTIVE" and campaign.signups_open and members < campaign.capacity,
        rewards_open=state == "ACTIVE" and pool >= campaign.level_1_reward_paise,
        payouts_open=at >= campaign.payout_opens_at,
    )


def reward_paise_for_level(campaign: Campaign, level: int) -> int:
    """The reward per verified referral at ``level``. Only level 1 is ever
    non-zero; levels 2-4 read columns the database pins at 0 (money-circulation
    rules), so this one formula drives the whole table without special cases."""
    return getattr(campaign, f"level_{level}_reward_paise", 0)


def reward_per_level(campaign: Campaign) -> list[dict[str, int]]:
    """The four-level table, each level's amount straight from its column."""
    return [
        {"level": level, "reward_per_user_paise": reward_paise_for_level(campaign, level)}
        for level in range(1, MAX_TRACKED_LEVEL + 1)
    ]


async def funded_total(db: AsyncSession) -> int:
    """Everything the admin has recorded into the promotional pool."""
    rows = await db.execute(
        select(LedgerEntry.amount_paise)
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(LedgerTransaction.kind == "FUNDING", LedgerAccount.kind == "PROMO_POOL")
    )
    return sum(rows.scalars())


async def public_config(db: AsyncSession) -> dict:
    campaign = await current_campaign(db)
    settings = await app_settings(db)
    g = await gates(db, campaign)
    at = timeutil.now()
    maintenance_on = settings.maintenance_active and (settings.maintenance_until is None or settings.maintenance_until > at)
    allocation = await funded_total(db) if campaign.show_promo_allocation else 0
    return {
        "server_now": timeutil.iso(at),
        "company_name": settings.company_name,
        "company_legal_name": settings.company_legal_name,
        "support_email": settings.support_email,
        "min_app_version": settings.min_app_version,
        "apk_download_url": settings.apk_download_url,
        "maintenance": {
            "active": maintenance_on,
            "message": settings.maintenance_message if maintenance_on else None,
            "until": timeutil.iso(settings.maintenance_until) if maintenance_on else None,
        },
        "campaign": {
            "status": g.status,
            "starts_at": timeutil.iso(campaign.starts_at),
            "ends_at": timeutil.iso(campaign.ends_at),
            "brand_reveal_at": timeutil.iso(campaign.brand_reveal_at),
            "launch_at": timeutil.iso(campaign.launch_at),
            "payout_opens_at": timeutil.iso(campaign.payout_opens_at),
            # Hidden until the reveal time, even if already entered.
            "brand_name": campaign.brand_name if at >= campaign.brand_reveal_at else None,
            "signups_open": g.signups_open,
            "rewards_open": g.rewards_open,
        },
        "rewards": {
            "levels": reward_per_level(campaign),
            "min_withdrawal_paise": campaign.min_withdrawal_paise,
        },
        "membership": {"verified_count": await verified_count(db), "capacity": campaign.capacity},
        "promotion": {"allocation_paise": allocation or None},
        "announcement": (
            {"text": settings.announcement_text, "tone": settings.announcement_tone or "info"}
            if settings.announcement_text
            else None
        ),
        "ads": {
            "banner_enabled": settings.ads_banner_enabled,
            "interstitial_enabled": settings.ads_interstitial_enabled,
            "rewarded_enabled": settings.ads_rewarded_enabled,
            "min_interstitial_interval_seconds": settings.ads_min_interstitial_interval_seconds,
        },
        "links": {
            "terms_url": settings.terms_url,
            "privacy_url": settings.privacy_url,
            "support_url": settings.support_url,
        },
    }

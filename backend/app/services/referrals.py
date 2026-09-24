"""Referral binding, counts, the level-1 list and daily snapshots.

The referrer is written once, at signup, together with up to four closure
rows. It can't be changed afterwards and a user can only be referred by an
account that already exists and is verified, so loops are impossible.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, ids, timeutil
from app.models import MAX_TRACKED_LEVEL, ReferralEdge, ReferralReward, ReferralSnapshot, User
from app.phone import mask_phone
from app.services import campaign as campaign_service
from app.services import jobs

SNAPSHOT_MAX_AGE = timedelta(hours=24)


async def find_referrer(db: AsyncSession, raw_code: str) -> User:
    code = ids.normalize_code(raw_code)
    if code is None:
        raise errors.ReferralCodeInvalid()
    referrer = (await db.execute(select(User).where(User.public_id == code))).scalar_one_or_none()
    if referrer is None or referrer.status != "ACTIVE":
        raise errors.ReferralCodeInvalid()
    return referrer


async def bind(db: AsyncSession, user: User, referrer: User) -> None:
    """Attach ``user`` below ``referrer``: level 1 plus the referrer's own
    ancestors shifted one level down, up to level 4."""
    rows = [{"ancestor_id": referrer.id, "descendant_id": user.id, "level": 1}]
    ancestors = await db.execute(
        select(ReferralEdge.ancestor_id, ReferralEdge.level).where(
            ReferralEdge.descendant_id == referrer.id, ReferralEdge.level < MAX_TRACKED_LEVEL
        )
    )
    for ancestor_id, level in ancestors:
        rows.append({"ancestor_id": ancestor_id, "descendant_id": user.id, "level": level + 1})
    await db.execute(insert(ReferralEdge).values(rows))


async def qualify(db: AsyncSession, user: User) -> None:
    """The user verified: their edges now count for every ancestor."""
    await db.execute(
        update(ReferralEdge)
        .where(ReferralEdge.descendant_id == user.id, ReferralEdge.status == "PENDING")
        .values(status="QUALIFIED", qualified_at=timeutil.now())
    )


async def direct_count(db: AsyncSession, user_id: int) -> int:
    """Live count of verified direct referrals (the dashboard; the table uses the snapshot)."""
    return (
        await db.execute(
            select(func.count())
            .select_from(ReferralEdge)
            .where(ReferralEdge.ancestor_id == user_id, ReferralEdge.level == 1, ReferralEdge.status == "QUALIFIED")
        )
    ).scalar_one()


async def level_one_pending_count(db: AsyncSession, user_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.referrer_id == user_id,
                User.status == "PENDING_VERIFICATION",
                User.pending_expires_at > timeutil.now(),
            )
        )
    ).scalar_one()


async def compute_snapshot(db: AsyncSession, user_id: int) -> ReferralSnapshot:
    counts = dict.fromkeys(range(1, MAX_TRACKED_LEVEL + 1), 0)
    result = await db.execute(
        select(ReferralEdge.level, func.count())
        .where(ReferralEdge.ancestor_id == user_id, ReferralEdge.status == "QUALIFIED")
        .group_by(ReferralEdge.level)
    )
    for level, count in result:
        counts[level] = count
    # Income is the sum of real reward records, never count × rate.
    income = (
        await db.execute(
            select(func.coalesce(func.sum(ReferralReward.amount_paise), 0)).where(
                ReferralReward.beneficiary_id == user_id, ReferralReward.status == "CREDITED"
            )
        )
    ).scalar_one()
    at = timeutil.now()
    values = {
        "snapshot_date": timeutil.ist_date(at),
        "level_1_count": counts[1],
        "level_2_count": counts[2],
        "level_3_count": counts[3],
        "level_4_count": counts[4],
        "level_1_income_paise": int(income),
        "generated_at": at,
    }
    stmt = insert(ReferralSnapshot).values(user_id=user_id, **values)
    await db.execute(stmt.on_conflict_do_update(index_elements=[ReferralSnapshot.user_id], set_=values))
    return (await db.execute(select(ReferralSnapshot).where(ReferralSnapshot.user_id == user_id))).scalar_one()


async def summary(db: AsyncSession, user: User) -> dict:
    snapshot = (await db.execute(select(ReferralSnapshot).where(ReferralSnapshot.user_id == user.id))).scalar_one_or_none()
    refresh_pending = False
    if snapshot is None:
        # First visit: small trees are cheap, so compute now.
        snapshot = await compute_snapshot(db, user.id)
    elif timeutil.now() - snapshot.generated_at >= SNAPSHOT_MAX_AGE:
        await jobs.enqueue(
            db,
            "snapshot_refresh",
            {"user_id": user.id},
            dedupe_key=f"snapshot:{user.id}:{timeutil.ist_date().isoformat()}",
        )
        refresh_pending = True

    campaign = await campaign_service.current_campaign(db)
    rates = {row["level"]: row["reward_per_user_paise"] for row in campaign_service.reward_per_level(campaign)}
    counts = [snapshot.level_1_count, snapshot.level_2_count, snapshot.level_3_count, snapshot.level_4_count]
    incomes = [
        snapshot.level_1_income_paise,
        snapshot.level_2_income_paise,
        snapshot.level_3_income_paise,
        snapshot.level_4_income_paise,
    ]
    levels = [
        {
            "level": level,
            "user_count": counts[level - 1],
            "reward_per_user_paise": rates[level],
            "total_reward_paise": incomes[level - 1],
        }
        for level in range(1, MAX_TRACKED_LEVEL + 1)
    ]
    return {
        "generated_at": timeutil.iso(snapshot.generated_at),
        "refresh_pending": refresh_pending,
        "levels": levels,
        "total_user_count": sum(counts),
        "total_reward_paise": sum(incomes),
        "level_1_pending_count": await level_one_pending_count(db, user.id),
    }


def _encode_cursor(created_at: datetime, row_id: int) -> str:
    raw = json.dumps([created_at.isoformat(), row_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created, row_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(created), int(row_id)
    except (ValueError, TypeError) as exc:
        raise errors.ValidationFailed(fields={"cursor": "Invalid cursor."}) from exc


async def direct_referrals(db: AsyncSession, user: User, limit: int, cursor: str | None) -> dict:
    """Level 1 only. Nobody deeper is ever listed."""
    limit = max(1, min(limit, 50))
    visible = or_(
        User.status.in_(("ACTIVE", "SUSPENDED")),
        and_(User.status == "PENDING_VERIFICATION", User.pending_expires_at > timeutil.now()),
    )
    query = (
        select(User, ReferralReward.amount_paise)
        .outerjoin(
            ReferralReward,
            and_(ReferralReward.source_user_id == User.id, ReferralReward.status == "CREDITED"),
        )
        .where(User.referrer_id == user.id, visible)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        created, row_id = _decode_cursor(cursor)
        query = query.where(or_(User.created_at < created, and_(User.created_at == created, User.id < row_id)))
    rows = (await db.execute(query)).all()
    items = [
        {
            "public_id": friend.public_id,
            "phone_masked": mask_phone(friend.phone),
            "status": "PENDING" if friend.status == "PENDING_VERIFICATION" else "VERIFIED",
            "joined_at": timeutil.iso(friend.created_at),
            "verified_at": timeutil.iso(friend.verified_at),
            "reward_paise": int(amount or 0),
        }
        for friend, amount in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return {"items": items, "next_cursor": next_cursor}

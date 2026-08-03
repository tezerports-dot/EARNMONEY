"""The activity rule and the money that follows from it.

A referred user counts for exactly ``PAYOUT_PER_ACTIVE`` INR in a given IST
month if and only if all three of these hold:

1. they are currently a member of the managed **channel** of their pair,
2. they are currently a member of the managed **group** of their pair,
3. they produced at least **one** recorded interaction in that IST month.

Membership on its own never counts. One interaction is enough: the status is
per-person-per-month, not per-click, so a thousand button taps still pay 10
INR once. Leaving either chat drops the user to inactive immediately, whatever
they did earlier in the month.

Nothing here is precomputed by a cron job — activity is derived on read, so a
user who leaves at 14:59 is already inactive at 15:00.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app import db
from app.config import settings
from app.timeutil import current_month

RATE = settings.payout_per_active


@dataclass(frozen=True)
class ActivityStatus:
    """Why a user is (or is not) active, in enough detail to explain it."""

    user_id: int
    uid: str
    month: str
    in_group: bool
    in_channel: bool
    interactions: int
    verified: bool
    duplicate: bool
    banned: bool

    @property
    def has_interaction(self) -> bool:
        return self.interactions > 0

    @property
    def eligible(self) -> bool:
        """Account-level eligibility, ignoring this month's behaviour."""
        return self.verified and not self.duplicate and not self.banned

    @property
    def active(self) -> bool:
        return (
            self.eligible and self.in_group and self.in_channel and self.has_interaction
        )

    @property
    def reason(self) -> str:
        if not self.verified:
            return "not verified (contact not shared)"
        if self.duplicate:
            return "duplicate phone number"
        if self.banned:
            return "banned"
        missing = []
        if not self.in_group:
            missing.append("not in group")
        if not self.in_channel:
            missing.append("not in channel")
        if not self.has_interaction:
            missing.append("no interaction this month")
        return ", ".join(missing) if missing else "active"


def _pair_chat_ids(user: sqlite3.Row) -> tuple[int | None, int | None]:
    pair_id = user["pair_id"]
    if not pair_id:
        return None, None
    pair = db.get_pair(int(pair_id))
    if pair is None:
        return None, None
    group_id = pair["group_chat_id"]
    channel_id = pair["channel_chat_id"]
    return (
        int(group_id) if group_id else None,
        int(channel_id) if channel_id else None,
    )


def status_for(user: sqlite3.Row, month: str | None = None) -> ActivityStatus:
    """Evaluate the three activity conditions for one user in one month."""
    month = month or current_month()
    group_id, channel_id = _pair_chat_ids(user)
    return ActivityStatus(
        user_id=int(user["id"]),
        uid=str(user["uid"]),
        month=month,
        in_group=db.is_member(int(user["id"]), group_id),
        in_channel=db.is_member(int(user["id"]), channel_id),
        interactions=db.activity_count(int(user["id"]), month),
        verified=bool(user["verified"]),
        duplicate=bool(user["duplicate"]),
        banned=bool(user["banned"]),
    )


def status_for_id(user_id: int, month: str | None = None) -> ActivityStatus | None:
    user = db.get_user(user_id)
    return None if user is None else status_for(user, month)


def is_active(user_id: int, month: str | None = None) -> bool:
    st = status_for_id(user_id, month)
    return bool(st and st.active)


@dataclass(frozen=True)
class ReferralBreakdown:
    user: sqlite3.Row
    status: ActivityStatus

    @property
    def amount(self) -> float:
        return RATE if self.status.active else 0.0


@dataclass(frozen=True)
class EarningsReport:
    uid: str
    month: str
    referrer_status: ActivityStatus
    rows: list[ReferralBreakdown]

    @property
    def total_referrals(self) -> int:
        return len(self.rows)

    @property
    def active_referrals(self) -> int:
        return sum(1 for row in self.rows if row.status.active)

    @property
    def inactive_referrals(self) -> int:
        return self.total_referrals - self.active_referrals

    @property
    def gross(self) -> float:
        """What the referrals are worth before the referrer's own gate."""
        return round(self.active_referrals * RATE, 2)

    @property
    def payable(self) -> bool:
        """The referrer must themselves be active to earn anything at all."""
        return self.referrer_status.active

    @property
    def amount(self) -> float:
        return self.gross if self.payable else 0.0

    @property
    def blocked_reason(self) -> str:
        return "" if self.payable else self.referrer_status.reason


def report_for(user: sqlite3.Row, month: str | None = None) -> EarningsReport:
    month = month or current_month()
    referred = db.referrals_of(str(user["uid"]))
    rows = [ReferralBreakdown(user=row, status=status_for(row, month)) for row in referred]
    return EarningsReport(
        uid=str(user["uid"]),
        month=month,
        referrer_status=status_for(user, month),
        rows=rows,
    )


def report_for_uid(uid: str, month: str | None = None) -> EarningsReport | None:
    user = db.get_user_by_uid(uid)
    return None if user is None else report_for(user, month)


def amount_for(user: sqlite3.Row, month: str | None = None) -> float:
    return report_for(user, month).amount


def leaderboard(month: str | None = None, limit: int = 20) -> list[tuple[sqlite3.Row, int, float]]:
    """``(user, active_referral_count, amount)`` for the top referrers."""
    month = month or current_month()
    referrer_uids = [
        row["referred_by_uid"]
        for row in db.query(
            "SELECT DISTINCT referred_by_uid FROM users WHERE referred_by_uid IS NOT NULL"
        )
    ]
    out: list[tuple[sqlite3.Row, int, float]] = []
    for uid in referrer_uids:
        user = db.get_user_by_uid(uid)
        if user is None:
            continue
        report = report_for(user, month)
        if report.active_referrals:
            out.append((user, report.active_referrals, report.amount))
    out.sort(key=lambda item: (-item[1], item[0]["uid"]))
    return out[:limit]


def month_totals(month: str | None = None) -> dict[str, float | int]:
    month = month or current_month()
    board = leaderboard(month, limit=10_000)
    return {
        "month": month,
        "earning_referrers": len(board),
        "active_referred": sum(count for _, count, _ in board),
        "total_inr": round(sum(amount for _, _, amount in board), 2),
    }

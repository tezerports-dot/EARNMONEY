"""The activity rule, and the two-level payout that follows from it.

Activity
--------
A downline member counts for a given IST month if and only if all three hold:

1. they are currently a member of the managed **channel** of their pair,
2. they are currently a member of the managed **group** of their pair,
3. they produced at least **one** recorded interaction in that IST month.

Membership on its own never counts. One interaction is enough: the status is
per-person-per-month, not per-click, so a thousand button taps pay the same as
one. Leaving either chat drops them to inactive immediately, whatever they did
earlier in the month.

Two levels
----------
Earnings run two levels deep::

    A ──refers──▶ B ──refers──▶ C
    │                            │
    └──── level 1: ₹L1 ──────────┘  for B
    └──── level 2: ₹L2 ─────────────for C

So if B also brings in D and E, A earns level 2 on C, D and E, while B earns
level 1 on each of them. Nothing goes deeper than that: C's own referrals pay
C (level 1) and B (level 2), but never A.

Each downline member is judged on **their own** activity. B being inactive
costs B their own earnings; it does not remove C, D or E from A's level-2
count.

The earner must still clear the bar themselves — verified, non-duplicate, in
both their chats, and at least one interaction that month — to be paid
anything at all.

Both rates live in the ``settings`` table and are editable from the admin
panel, so they are read fresh on every calculation rather than frozen at
import time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app import db
from app.timeutil import current_month

LEVEL1 = 1
LEVEL2 = 2


@dataclass(frozen=True)
class Rates:
    """Current INR-per-active-member rates, per level."""

    level1: float
    level2: float

    def of(self, level: int) -> float:
        return self.level1 if level == LEVEL1 else self.level2

    @property
    def total(self) -> float:
        """What one full A→B→C chain is worth to the person at the top."""
        return round(self.level1 + self.level2, 2)


def rates() -> Rates:
    return Rates(
        level1=db.get_setting_float("payout_level1", 5.0),
        level2=db.get_setting_float("payout_level2", 5.0),
    )


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
class DownlineRow:
    """One person below the earner, at level 1 or level 2."""

    user: sqlite3.Row
    status: ActivityStatus
    level: int
    rate: float
    via_uid: str | None = None  # level 2 only: who introduced them

    @property
    def amount(self) -> float:
        return self.rate if self.status.active else 0.0

    @property
    def name(self) -> str:
        return str(
            self.user["full_name"] or self.user["username"] or self.user["uid"]
        )


@dataclass(frozen=True)
class EarningsReport:
    uid: str
    month: str
    referrer_status: ActivityStatus
    rows: list[DownlineRow]
    rates: Rates

    # -- level 1 (direct) --------------------------------------------------- #

    @property
    def level1_rows(self) -> list[DownlineRow]:
        return [row for row in self.rows if row.level == LEVEL1]

    @property
    def total_referrals(self) -> int:
        return len(self.level1_rows)

    @property
    def active_referrals(self) -> int:
        return sum(1 for row in self.level1_rows if row.status.active)

    @property
    def inactive_referrals(self) -> int:
        return self.total_referrals - self.active_referrals

    @property
    def level1_amount(self) -> float:
        return round(sum(row.amount for row in self.level1_rows), 2)

    # -- level 2 (indirect) ------------------------------------------------- #

    @property
    def level2_rows(self) -> list[DownlineRow]:
        return [row for row in self.rows if row.level == LEVEL2]

    @property
    def total_indirect(self) -> int:
        return len(self.level2_rows)

    @property
    def active_indirect(self) -> int:
        return sum(1 for row in self.level2_rows if row.status.active)

    @property
    def inactive_indirect(self) -> int:
        return self.total_indirect - self.active_indirect

    @property
    def level2_amount(self) -> float:
        return round(sum(row.amount for row in self.level2_rows), 2)

    # -- totals ------------------------------------------------------------- #

    @property
    def total_downline(self) -> int:
        return len(self.rows)

    @property
    def active_downline(self) -> int:
        return self.active_referrals + self.active_indirect

    @property
    def gross(self) -> float:
        """What both levels are worth before the earner's own gate."""
        return round(self.level1_amount + self.level2_amount, 2)

    @property
    def payable(self) -> bool:
        """The earner must themselves be active to receive anything."""
        return self.referrer_status.active

    @property
    def amount(self) -> float:
        return self.gross if self.payable else 0.0

    @property
    def blocked_reason(self) -> str:
        return "" if self.payable else self.referrer_status.reason


def report_for(user: sqlite3.Row, month: str | None = None) -> EarningsReport:
    month = month or current_month()
    uid = str(user["uid"])
    current = rates()

    rows = [
        DownlineRow(
            user=row,
            status=status_for(row, month),
            level=LEVEL1,
            rate=current.level1,
        )
        for row in db.referrals_of(uid)
    ]
    rows += [
        DownlineRow(
            user=row,
            status=status_for(row, month),
            level=LEVEL2,
            rate=current.level2,
            via_uid=str(row["via_uid"]),
        )
        for row in db.level2_referrals_of(uid)
    ]

    return EarningsReport(
        uid=uid,
        month=month,
        referrer_status=status_for(user, month),
        rows=rows,
        rates=current,
    )


def report_for_uid(uid: str, month: str | None = None) -> EarningsReport | None:
    user = db.get_user_by_uid(uid)
    return None if user is None else report_for(user, month)


def amount_for(user: sqlite3.Row, month: str | None = None) -> float:
    return report_for(user, month).amount


def _earner_candidates() -> list[str]:
    """UIDs that could possibly earn: anyone with at least one direct referral.

    Level 2 always has a level-1 member in between, so nobody outside this set
    can have downline income.
    """
    return [
        str(row["referred_by_uid"])
        for row in db.query(
            "SELECT DISTINCT referred_by_uid FROM users WHERE referred_by_uid IS NOT NULL"
        )
    ]


def leaderboard(
    month: str | None = None, limit: int = 20
) -> list[tuple[sqlite3.Row, EarningsReport]]:
    """``(user, report)`` for the top earners, best first."""
    month = month or current_month()
    out: list[tuple[sqlite3.Row, EarningsReport]] = []
    for uid in _earner_candidates():
        user = db.get_user_by_uid(uid)
        if user is None:
            continue
        report = report_for(user, month)
        if report.active_downline:
            out.append((user, report))
    out.sort(key=lambda item: (-item[1].gross, -item[1].active_downline, item[0]["uid"]))
    return out[:limit]


def month_totals(month: str | None = None) -> dict[str, float | int | str]:
    month = month or current_month()
    board = leaderboard(month, limit=10_000)
    return {
        "month": month,
        "earning_referrers": len(board),
        "active_referred": sum(report.active_referrals for _, report in board),
        "active_indirect": sum(report.active_indirect for _, report in board),
        "active_downline": sum(report.active_downline for _, report in board),
        "total_inr": round(sum(report.amount for _, report in board), 2),
    }

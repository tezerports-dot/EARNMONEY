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
from app.timeutil import current_month, month_to_int

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
    interacted: bool
    verified: bool
    duplicate: bool
    banned: bool

    @property
    def has_interaction(self) -> bool:
        """Did they interact at all that month?

        A boolean, not a count: the rule only ever asks *whether*, and storing
        a per-tap counter would mean writing on every button press for no
        change in anyone's payout.
        """
        return self.interacted

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

    @property
    def out_of_horizon(self) -> bool:
        """True when the month is older than the two we keep activity for."""
        return self.month not in db.activity_horizon()


def status_for(user: sqlite3.Row, month: str | None = None) -> ActivityStatus:
    """Evaluate the three activity conditions for one user in one month.

    Every input is a column on the user's own row — the two membership bits
    and the two month markers — so this is one row read, no joins, whether
    there are ten users or thirty million.
    """
    month = month or current_month()
    return ActivityStatus(
        user_id=int(user["id"]),
        uid=str(user["uid"]),
        month=month,
        in_group=db.has_flag(user, db.F_IN_GROUP),
        in_channel=db.has_flag(user, db.F_IN_CHANNEL),
        interacted=db.was_active_in(user, month),
        verified=db.has_flag(user, db.F_VERIFIED),
        duplicate=db.has_flag(user, db.F_DUPLICATE),
        banned=db.has_flag(user, db.F_BANNED),
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
        """Display label. Names are not stored, so the UID *is* the name."""
        return str(self.user["uid"])


@dataclass(frozen=True)
class EarningsReport:
    """What one member earns, and the downline it came from.

    The counts and the money come from SQL aggregates, not from ``rows``:
    ``rows`` is a *display* sample capped at :data:`ROW_LIMIT`, so a member
    with a hundred thousand referrals is still paid exactly right while the
    page renders the first page of them.
    """

    uid: str
    month: str
    referrer_status: ActivityStatus
    rows: list[DownlineRow]
    rates: Rates
    total_referrals: int
    total_indirect: int
    active_referrals: int
    active_indirect: int
    truncated: bool = False

    # -- level 1 (direct) --------------------------------------------------- #

    @property
    def level1_rows(self) -> list[DownlineRow]:
        return [row for row in self.rows if row.level == LEVEL1]

    @property
    def inactive_referrals(self) -> int:
        return self.total_referrals - self.active_referrals

    @property
    def level1_amount(self) -> float:
        return round(self.active_referrals * self.rates.level1, 2)

    # -- level 2 (indirect) ------------------------------------------------- #

    @property
    def level2_rows(self) -> list[DownlineRow]:
        return [row for row in self.rows if row.level == LEVEL2]

    @property
    def inactive_indirect(self) -> int:
        return self.total_indirect - self.active_indirect

    @property
    def level2_amount(self) -> float:
        return round(self.active_indirect * self.rates.level2, 2)

    # -- totals ------------------------------------------------------------- #

    @property
    def total_downline(self) -> int:
        return self.total_referrals + self.total_indirect

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


ROW_LIMIT = 250  # per level, for display only — never used for the payout


def report_for(
    user: sqlite3.Row, month: str | None = None, row_limit: int = ROW_LIMIT
) -> EarningsReport:
    month = month or current_month()
    uid = str(user["uid"])
    current = rates()

    total1, total2 = db.count_downline(uid)
    active1, active2 = db.count_active_downline(uid, month)

    level1 = db.referrals_of(uid, limit=row_limit)
    level2 = db.level2_referrals_of(uid, limit=row_limit)

    rows = [
        DownlineRow(user=row, status=status_for(row, month), level=LEVEL1,
                    rate=current.level1)
        for row in level1
    ]
    rows += [
        DownlineRow(user=row, status=status_for(row, month), level=LEVEL2,
                    rate=current.level2, via_uid=str(row["via_uid"]))
        for row in level2
    ]

    return EarningsReport(
        uid=uid,
        month=month,
        referrer_status=status_for(user, month),
        rows=rows,
        rates=current,
        total_referrals=total1,
        total_indirect=total2,
        active_referrals=active1,
        active_indirect=active2,
        truncated=len(level1) < total1 or len(level2) < total2,
    )


def report_for_uid(uid: str, month: str | None = None) -> EarningsReport | None:
    user = db.get_user_by_uid(uid)
    return None if user is None else report_for(user, month)


def amount_for(user: sqlite3.Row, month: str | None = None) -> float:
    return report_for(user, month).amount


@dataclass(frozen=True)
class Standing:
    """One earner's position, built from aggregates rather than full reports."""

    uid: str
    active_referrals: int
    active_indirect: int
    rates: Rates
    payable: bool

    @property
    def total_referrals(self) -> int:  # kept for template compatibility
        return self.active_referrals

    @property
    def total_indirect(self) -> int:
        return self.active_indirect

    @property
    def gross(self) -> float:
        return round(
            self.active_referrals * self.rates.level1
            + self.active_indirect * self.rates.level2,
            2,
        )

    @property
    def amount(self) -> float:
        return self.gross if self.payable else 0.0

    @property
    def active_downline(self) -> int:
        return self.active_referrals + self.active_indirect


def standings(month: str | None = None, limit: int | None = None) -> list[Standing]:
    """The top earners for a month, ranked, in a single query.

    Both levels, the counts and each earner's own eligibility come out of one
    grouped scan — never a query per member. ``limit`` is applied in SQL, so
    asking for the top 50 out of thirty million costs the scan and nothing
    more.
    """
    month = month or current_month()
    current = rates()
    return [
        Standing(
            uid=str(row["uid"]),
            active_referrals=int(row["l1"]),
            active_indirect=int(row["l2"]),
            rates=current,
            payable=(
                (int(row["flags"] or 0) & db.COUNTABLE_MASK) == db.COUNTABLE_VALUE
                and month_to_int(month) in (row["active_month"], row["prev_month"])
            ),
        )
        for row in db.standings_rows(month, current.level1, current.level2, limit)
    ]


BOARD_CACHE_SIZE = 50


def compute_board(month: str) -> list[dict[str, object]]:
    """Top earners as plain data, so it can be snapshotted as JSON."""
    return [
        {
            "uid": item.uid,
            "l1": item.active_referrals,
            "l2": item.active_indirect,
            "payable": item.payable,
        }
        for item in standings(month, limit=BOARD_CACHE_SIZE)
    ]


def leaderboard(
    month: str | None = None, limit: int = 20
) -> list[tuple[sqlite3.Row, Standing]]:
    """``(user, standing)`` for the top earners, best first.

    Live below :data:`db.LIVE_AGGREGATE_LIMIT`; above it, served from the
    snapshot the daily job refreshes — the ranking is a scan of the whole
    member base and does not need to be second-fresh.
    """
    month = month or current_month()
    current = rates()

    if month != current_month() or db.aggregates_are_live():
        board = compute_board(month)
    else:
        board, _ = db.cached_snapshot("board_cache", lambda: compute_board(month))

    out: list[tuple[sqlite3.Row, Standing]] = []
    for entry in board[:limit]:
        user = db.get_user_by_uid(str(entry["uid"]))
        if user is None:
            continue
        out.append(
            (
                user,
                Standing(
                    uid=str(entry["uid"]),
                    active_referrals=int(entry["l1"]),
                    active_indirect=int(entry["l2"]),
                    rates=current,
                    payable=bool(entry["payable"]),
                ),
            )
        )
    return out


def compute_month_totals(month: str | None = None) -> dict[str, float | int | str]:
    """Fleet-wide totals, computed entirely in SQL."""
    month = month or current_month()
    current = rates()
    totals = db.standings_totals(month, current.level1, current.level2)
    return {
        "month": month,
        "earning_referrers": totals["earners"],
        "active_referred": totals["a1"],
        "active_indirect": totals["a2"],
        "active_downline": totals["a1"] + totals["a2"],
        "total_inr": round(totals["payable"], 2),
    }


def month_totals(month: str | None = None) -> dict[str, float | int | str]:
    """Totals for the dashboard — live when cheap, snapshotted when not.

    Only the current month is snapshotted; asking for a past month always
    computes, because that happens once at payout time rather than on every
    page view.
    """
    month = month or current_month()
    if month != current_month() or db.aggregates_are_live():
        return compute_month_totals(month)
    value, taken = db.cached_snapshot(
        "totals_cache", lambda: compute_month_totals(month)
    )
    value["snapshot_at"] = taken
    return value

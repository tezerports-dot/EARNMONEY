"""The one clock the backend uses.

Business rules (payout date, expiry, snapshots) read time from ``now()`` rather
than the database's ``now()`` so tests can move the clock.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


def freeze(at: datetime | None) -> None:
    """Pin ``now()`` to ``at`` (tests only). ``None`` releases it."""
    global _frozen
    if at is not None and at.tzinfo is None:
        raise ValueError("freeze() needs an aware datetime")
    _frozen = at


def ist_date(at: datetime | None = None) -> date:
    return (at or now()).astimezone(IST).date()


def iso(at: datetime | None) -> str | None:
    if at is None:
        return None
    return at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

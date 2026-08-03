"""Time helpers.

Every month boundary in this project is an *Indian* month: it starts on the
1st at 00:00:00 IST and ends on the last day at 23:59:59.999999 IST. Payout
periods, activity buckets and withdrawal months all use that definition.

Timestamps are stored in the database as ISO-8601 strings in UTC with a
trailing ``Z``; month keys (``YYYY-MM``) are always derived in IST so that a
row written at 23:00 UTC on the 31st belongs to the *next* Indian month.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_ist() -> datetime:
    return datetime.now(IST)


def iso_utc(dt: datetime | None = None) -> str:
    """Serialise a datetime as an ISO-8601 UTC string ending in ``Z``."""
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_ist(value: str | datetime | None) -> datetime | None:
    dt = parse_iso(value) if isinstance(value, str) else value
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def month_key(value: str | datetime | None = None) -> str:
    """Return the ``YYYY-MM`` IST month a timestamp falls into."""
    dt = to_ist(value) if value is not None else now_ist()
    if dt is None:
        dt = now_ist()
    return dt.strftime("%Y-%m")


def current_month() -> str:
    return now_ist().strftime("%Y-%m")


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """Return ``(start, end)`` as IST-aware datetimes for a ``YYYY-MM`` key.

    ``start`` is the 1st at 00:00:00 IST, ``end`` is the first instant of the
    following month, so a half-open ``[start, end)`` comparison is exact and
    needs no leap-second or 23:59:59 fudging.
    """
    year, mon = (int(part) for part in month.split("-"))
    start = datetime(year, mon, 1, tzinfo=IST)
    if mon == 12:
        end = datetime(year + 1, 1, 1, tzinfo=IST)
    else:
        end = datetime(year, mon + 1, 1, tzinfo=IST)
    return start, end


def month_bounds_utc(month: str) -> tuple[str, str]:
    """``month_bounds`` expressed as the ISO-UTC strings stored in the DB."""
    start, end = month_bounds(month)
    return iso_utc(start), iso_utc(end)


def shift_month(month: str, delta: int) -> str:
    year, mon = (int(part) for part in month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def recent_months(count: int = 12, end: str | None = None) -> list[str]:
    """Newest-first list of month keys ending at ``end`` (default: now)."""
    end = end or current_month()
    return [shift_month(end, -offset) for offset in range(count)]


def human_ist(value: str | datetime | None) -> str:
    dt = to_ist(value)
    return dt.strftime("%d %b %Y, %H:%M IST") if dt else "-"


def seconds_until_ist_hour(hour: int) -> float:
    """Seconds to wait until the next occurrence of ``hour``:00 IST."""
    now = now_ist()
    target = now.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())

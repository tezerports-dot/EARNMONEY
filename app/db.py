"""SQLite access layer, sized for millions of users on one small machine.

Storage policy
--------------
Only what a payout actually needs is kept. Everything else is either derived
at read time or never written at all:

* **No per-interaction log.** The rule only ever asks "did this person
  interact during month M?", which is one fact per person per month, not one
  row per tap. Two integer columns on the user row (``active_month``,
  ``prev_month``) answer it, so a member who taps a thousand buttons causes
  at most **one** write all month.
* **No memberships table.** A user belongs to exactly one pair — one group
  and one channel — so their membership is two bits in ``users.flags``
  instead of two rows.
* **No invite-link table.** Only the short link hash is kept, on the user
  row; attribution works off the link *name* (the UID), which Telegram
  reports on join and which costs nothing to store.
* **No profile data.** Usernames, display names, message counts and
  last-seen timestamps are never written — Telegram sends the current name
  with every update, so the bots display it live and the database holds less
  personal data.
* **Phone numbers** are a truncated 16-byte SHA-256 (BLOB, not hex text),
  which is only ever used to reject a second account.

The permanent record of money is the ``withdrawals`` row, which is written
once per payout and is tiny. Activity history is deliberately two months
deep — the current month plus the previous one — which covers the whole
payout window; see docs/SCALING.md.

Design notes
------------
* One connection per operation, handed out by :func:`connect`. WAL mode lets
  the FastAPI request handlers and the bot polling tasks read concurrently
  while a single writer commits.
* ``users.id`` is the *Telegram user id*. Telegram ids are global, so every
  bot in the fleet sees the same id for the same person and all foreign keys
  line up without a mapping table.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from app.config import settings
from app.ids import random_uid
from app.timeutil import (
    current_month,
    current_month_int,
    iso_utc,
    month_to_int,
    now_utc,
)

SCHEMA_VERSION = "2"

# SQLite serialises writers itself, but a process-wide lock keeps the
# "read, decide, write" sequences in this module atomic against each other.
_write_lock = threading.RLock()

# users.flags bits. Packing five booleans into one integer keeps the row at a
# single byte for all of them instead of five separate columns.
F_VERIFIED = 1
F_DUPLICATE = 2
F_BANNED = 4
F_IN_GROUP = 8
F_IN_CHANNEL = 16

FLAG_NAMES = {
    "verified": F_VERIFIED,
    "duplicate": F_DUPLICATE,
    "banned": F_BANNED,
    "in_group": F_IN_GROUP,
    "in_channel": F_IN_CHANNEL,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY,   -- Telegram user id
    uid          TEXT    NOT NULL,      -- public id, UID-XXXXXX
    referred_by  TEXT,                  -- referrer's uid
    phone_hash   BLOB,                  -- 16-byte truncated SHA-256
    flags        INTEGER NOT NULL DEFAULT 0,
    pair_id      INTEGER,
    joined_at    INTEGER NOT NULL,      -- unix epoch seconds
    active_month INTEGER,               -- YYYYMM of the latest interaction
    prev_month   INTEGER,               -- YYYYMM of the one before that
    group_invite TEXT,                  -- t.me/+<hash>, hash only
    chan_invite  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uid ON users(uid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone
    ON users(phone_hash) WHERE phone_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_ref ON users(referred_by);

CREATE TABLE IF NOT EXISTS bots (
    bot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'main',
    status      TEXT NOT NULL DEFAULT 'stopped',
    username    TEXT,
    telegram_id INTEGER,
    last_error  TEXT,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id   INTEGER NOT NULL,
    bot_id    INTEGER NOT NULL,
    chat_type TEXT NOT NULL,               -- 'group' | 'channel'
    title     TEXT,
    pair_id   INTEGER,
    added_at  TEXT NOT NULL,
    PRIMARY KEY (chat_id, bot_id)
);

CREATE TABLE IF NOT EXISTS pairs (
    pair_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    group_chat_id   INTEGER,
    channel_chat_id INTEGER,
    is_default      INTEGER NOT NULL DEFAULT 0,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    capacity        INTEGER NOT NULL DEFAULT 0,   -- 0 = unlimited
    closed          INTEGER NOT NULL DEFAULT 0,
    member_count    INTEGER NOT NULL DEFAULT 0,   -- maintained incrementally
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_details (
    user_id        INTEGER PRIMARY KEY,
    full_name      TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc           TEXT NOT NULL,
    upi_id         TEXT NOT NULL,
    submitted_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    month        INTEGER NOT NULL,        -- YYYYMM
    amount       REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   INTEGER NOT NULL,
    processed_at INTEGER,
    note         TEXT,
    UNIQUE (user_id, month)
);
CREATE INDEX IF NOT EXISTS idx_withdrawals_month ON withdrawals(month, status);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,
    user_id    INTEGER,
    event_type TEXT NOT NULL,
    payload    TEXT
);

CREATE TABLE IF NOT EXISTS warnings (
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
) WITHOUT ROWID;
"""

DEFAULT_SETTINGS = {
    # Two-level payout rates, in INR per active downline member per month.
    # Seeded from the environment on first boot, edited in the admin panel
    # afterwards.
    "payout_level1": f"{settings.payout_level1:g}",
    "payout_level2": f"{settings.payout_level2:g}",
    "daily_prompt_text": (
        "💳 <b>Daily reminder</b>\n\n"
        "Payouts go out by bank transfer once a month. If you have not "
        "submitted your bank details yet, open the main bot and send /bank — "
        "it asks for your name, account number, IFSC and UPI id one at a time."
    ),
    "daily_prompt_dm": "1",
    "daily_prompt_dm_limit": "2000",
    "broadcast_confirm": "1",
    "moderation_enabled": "1",
    "flood_limit": "6",
    "flood_window_seconds": "8",
    "warn_mute_at": "3",
    "warn_ban_at": "5",
    "mute_minutes": "60",
    "block_links_from_unverified": "1",
    "banned_words": "",
    "event_retention": "20000",
    "welcome_text": (
        "👋 <b>Welcome!</b>\n\n"
        "Tap the button below once. It shares your contact, verifies you, "
        "puts you in your group and channel, and gives you your ID and "
        "referral link — all in one step."
    ),
}


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    # 64 MB of page cache. The hot set at scale is the uid and phone indexes;
    # the OS page cache handles the rest without this process growing.
    conn.execute("PRAGMA cache_size=-64000")


@contextmanager
def connect(write: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a connection for the duration of one operation."""
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if write:
        _write_lock.acquire()
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    try:
        _configure(conn)
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        # executescript() commits implicitly, so the transaction may already be
        # closed by the time we get here.
        if write and conn.in_transaction:
            conn.execute("COMMIT")
    except Exception:
        if write and conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise
    finally:
        conn.close()
        if write:
            _write_lock.release()


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


def scalar(sql: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
    row = query_one(sql, params)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    with connect(write=True) as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or cur.rowcount


class SchemaMismatch(RuntimeError):
    """Raised when the database on disk predates the slim schema."""


def init_db() -> None:
    with connect(write=True) as conn:
        legacy = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name IN ('user_activity', 'memberships', 'invite_links')"
        ).fetchall()
        if legacy:
            raise SchemaMismatch(
                "This database uses the old high-volume schema "
                f"({', '.join(row['name'] for row in legacy)}). The current "
                "schema stores far less per user and is not a drop-in "
                "migration. Point DB_PATH at a new file, or see "
                "docs/MANAGEMENT.md for the migration steps."
            )
        conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )
        conn.execute(
            "INSERT INTO settings(key, value) VALUES ('schema_version', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )


def epoch() -> int:
    return int(now_utc().timestamp())


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return default if row is None or row["value"] is None else str(row["value"])


def get_setting_int(key: str, default: int) -> int:
    try:
        return int(get_setting(key, str(default)) or default)
    except ValueError:
        return default


def get_setting_float(key: str, default: float) -> float:
    try:
        return float(get_setting(key, str(default)) or default)
    except ValueError:
        return default


def get_setting_bool(key: str, default: bool = False) -> bool:
    return get_setting(key, "1" if default else "0").strip() in {"1", "true", "yes", "on"}


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def all_settings() -> dict[str, str]:
    return {row["key"]: row["value"] or "" for row in query("SELECT key, value FROM settings")}


# --------------------------------------------------------------------------- #
# events / audit
# --------------------------------------------------------------------------- #

def log_event(event_type: str, user_id: int | None = None, payload: str = "") -> None:
    execute(
        "INSERT INTO events(ts, user_id, event_type, payload) VALUES (?, ?, ?, ?)",
        (epoch(), user_id, event_type, payload[:300]),
    )


def recent_events(limit: int = 200, user_id: int | None = None) -> list[sqlite3.Row]:
    if user_id is not None:
        return query(
            "SELECT * FROM events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
    return query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


def prune_events() -> int:
    """Keep the audit log to the most recent ``event_retention`` rows.

    The log is an operational aid, not a legal record — the withdrawals table
    is what documents money. Left alone it would be the one table that grows
    without bound.
    """
    keep = get_setting_int("event_retention", 20_000)
    with connect(write=True) as conn:
        row = conn.execute("SELECT MAX(id) AS top FROM events").fetchone()
        if row is None or row["top"] is None:
            return 0
        cutoff = int(row["top"]) - keep
        if cutoff <= 0:
            return 0
        cur = conn.execute("DELETE FROM events WHERE id <= ?", (cutoff,))
        return cur.rowcount or 0


def prune_warnings(older_than_days: int = 90) -> int:
    cutoff = epoch() - older_than_days * 86_400
    return execute("DELETE FROM warnings WHERE updated_at < ?", (cutoff,))


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #

def get_user(user_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_uid(uid: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE uid = ?", (uid,))


def get_user_by_phone_hash(phone_hash: bytes) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE phone_hash = ?", (phone_hash,))


def has_flag(user: sqlite3.Row | None, flag: int) -> bool:
    return user is not None and bool(int(user["flags"] or 0) & flag)


def set_flag(user_id: int, flag: int, on: bool = True) -> None:
    if on:
        execute("UPDATE users SET flags = flags | ? WHERE id = ?", (flag, user_id))
    else:
        execute("UPDATE users SET flags = flags & ~? WHERE id = ?", (flag, user_id))


def set_flags(user_id: int, **named: bool) -> None:
    """Set several flags in one statement, e.g. ``set_flags(id, banned=True)``."""
    on = 0
    off = 0
    for name, value in named.items():
        bit = FLAG_NAMES[name]
        if value:
            on |= bit
        else:
            off |= bit
    if on or off:
        execute(
            "UPDATE users SET flags = (flags | ?) & ~? WHERE id = ?", (on, off, user_id)
        )


def create_user(user_id: int, referred_by: str | None = None) -> sqlite3.Row:
    """Insert a user with a collision-safe UID, or return the existing row.

    ``/start`` is idempotent: a repeat call never creates a second row and
    never rewrites an existing referrer, though it will fill in one that was
    previously absent.
    """
    with connect(write=True) as conn:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is not None:
            if existing["referred_by"] is None and referred_by:
                conn.execute(
                    "UPDATE users SET referred_by = ? WHERE id = ?", (referred_by, user_id)
                )
                return conn.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            return existing

        now = epoch()
        for _ in range(25):  # retry on the (astronomically rare) UID collision
            uid = random_uid()
            try:
                conn.execute(
                    "INSERT INTO users(id, uid, referred_by, joined_at) VALUES (?, ?, ?, ?)",
                    (user_id, uid, referred_by, now),
                )
                break
            except sqlite3.IntegrityError as exc:
                if "users.uid" not in str(exc) and "idx_users_uid" not in str(exc):
                    raise
        else:
            raise RuntimeError("could not allocate a unique UID after 25 attempts")
        conn.execute(
            "INSERT INTO settings(key, value) VALUES ('user_count', '1')"
            " ON CONFLICT(key) DO UPDATE SET"
            " value = CAST(CAST(settings.value AS INTEGER) + 1 AS TEXT)"
        )
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_user_fields(user_id: int, **fields: Any) -> None:
    allowed = {
        "phone_hash",
        "referred_by",
        "pair_id",
        "group_invite",
        "chan_invite",
        "active_month",
        "prev_month",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    execute(f"UPDATE users SET {assignments} WHERE id = ?", (*updates.values(), user_id))


def count_users(where: str = "", params: Sequence[Any] = ()) -> int:
    clause = f" WHERE {where}" if where else ""
    return int(scalar(f"SELECT COUNT(*) FROM users{clause}", params))


def list_users(search: str = "", limit: int = 100, offset: int = 0) -> list[sqlite3.Row]:
    """Search by UID or Telegram id.

    There is deliberately no name search: names are never stored, so the only
    stable handles are the public UID and the numeric Telegram id.
    """
    term = search.strip()
    if term:
        from app.ids import normalise_uid

        uid = normalise_uid(term)
        if uid:
            return query("SELECT * FROM users WHERE uid = ?", (uid,))
        if term.isdigit():
            return query("SELECT * FROM users WHERE id = ?", (int(term),))
        return []
    return query(
        "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?", (limit, offset)
    )


def referrals_of(uid: str, limit: int = 1000) -> list[sqlite3.Row]:
    """Level 1: the people this user introduced directly.

    Bounded — the payout is computed from ``count_active_downline``, so this
    list only ever has to be big enough to show.
    """
    return query(
        "SELECT * FROM users WHERE referred_by = ? AND uid <> ?"
        " ORDER BY joined_at DESC LIMIT ?",
        (uid, uid, limit),
    )


def level2_referrals_of(uid: str, limit: int = 1000) -> list[sqlite3.Row]:
    """Level 2: the people *their* direct referrals introduced.

    Each row carries ``via_uid`` — the level-1 member who brought them in — so
    the breakdown can show the chain. ``c.uid <> ?`` guards the one cycle the
    data allows: A refers B, then A later opens B's link and becomes B's
    referral, which would otherwise make A their own level-2 downline.
    """
    return query(
        "SELECT c.*, b.uid AS via_uid FROM users c"
        " JOIN users b ON b.uid = c.referred_by"
        " WHERE b.referred_by = ? AND b.uid <> ? AND c.uid <> ?"
        " ORDER BY c.joined_at DESC LIMIT ?",
        (uid, uid, uid, limit),
    )


# --------------------------------------------------------------------------- #
# activity — two integers, not a table
# --------------------------------------------------------------------------- #

def record_activity(user_id: int) -> bool:
    """Mark this user as having interacted during the current IST month.

    Returns True if anything was written. The row is only touched when the
    month actually changes, so a member who taps a hundred buttons in a month
    costs exactly one write — the whole reason there is no activity log.
    """
    month = current_month_int()
    row = query_one("SELECT active_month FROM users WHERE id = ?", (user_id,))
    if row is None or row["active_month"] == month:
        return False
    execute(
        "UPDATE users SET prev_month = active_month, active_month = ?"
        " WHERE id = ? AND (active_month IS NULL OR active_month <> ?)",
        (month, user_id, month),
    )
    return True


def was_active_in(user: sqlite3.Row | None, month: str) -> bool:
    """Did this user interact during ``month`` (``YYYY-MM``)?

    History is two months deep — the current month and the previous one —
    which spans the payout window. Older months are reported as inactive
    because the data is genuinely gone; the withdrawals row is the permanent
    record of what was paid.
    """
    if user is None:
        return False
    target = month_to_int(month)
    return target in (user["active_month"], user["prev_month"])


def activity_horizon() -> list[str]:
    """The months for which activity can still be answered."""
    from app.timeutil import shift_month

    now = current_month()
    return [now, shift_month(now, -1)]


# A user is countable when verified, not duplicate, not banned, and in both
# of their chats. Expressed as one mask so the aggregate queries can test it
# with a single integer comparison instead of five.
COUNTABLE_MASK = F_VERIFIED | F_DUPLICATE | F_BANNED | F_IN_GROUP | F_IN_CHANNEL
COUNTABLE_VALUE = F_VERIFIED | F_IN_GROUP | F_IN_CHANNEL


def active_user_count(month: str | None = None) -> int:
    target = month_to_int(month or current_month())
    return int(
        scalar(
            "SELECT COUNT(*) FROM users WHERE active_month = ? OR prev_month = ?",
            (target, target),
        )
    )


def _standings_subquery() -> str:
    """One row per (earner, downline member), tagged with the level.

    Both levels are gathered in a single pass and the earner's *own* row is
    joined in at the same time, so building the leaderboard never needs a
    lookup per earner — that turned into 150,000 queries at 300k members and
    took 35 seconds.
    """
    countable = "(u.flags & ?) = ? AND (u.active_month = ? OR u.prev_month = ?)"
    return f"""
        SELECT r.uid AS uid, r.flags AS flags,
               r.active_month AS active_month, r.prev_month AS prev_month,
               1 AS l1, 0 AS l2
          FROM users u
          JOIN users r ON r.uid = u.referred_by
         WHERE u.uid <> r.uid AND {countable}
        UNION ALL
        SELECT r.uid AS uid, r.flags AS flags,
               r.active_month AS active_month, r.prev_month AS prev_month,
               0 AS l1, 1 AS l2
          FROM users u
          JOIN users b ON b.uid = u.referred_by
          JOIN users r ON r.uid = b.referred_by
         WHERE u.uid <> r.uid AND b.uid <> r.uid AND {countable}
    """


def _countable_params(month: str) -> tuple[int, int, int, int]:
    target = month_to_int(month)
    return (COUNTABLE_MASK, COUNTABLE_VALUE, target, target)


def standings_rows(
    month: str, rate1: float, rate2: float, limit: int | None = None
) -> list[sqlite3.Row]:
    """Every earner's active downline counts, richest first, in one query."""
    params = _countable_params(month)
    tail = f" LIMIT {int(limit)}" if limit else ""
    return query(
        "SELECT uid, MAX(flags) AS flags, MAX(active_month) AS active_month,"
        " MAX(prev_month) AS prev_month, SUM(l1) AS l1, SUM(l2) AS l2"
        f" FROM ({_standings_subquery()}) GROUP BY uid"
        " ORDER BY (SUM(l1) * ? + SUM(l2) * ?) DESC, uid" + tail,
        (*params, *params, rate1, rate2),
    )


def standings_totals(month: str, rate1: float, rate2: float) -> dict[str, float]:
    """Fleet-wide monthly totals without materialising a row per earner."""
    params = _countable_params(month)
    target = month_to_int(month)
    row = query_one(
        "SELECT COUNT(*) AS earners, COALESCE(SUM(l1), 0) AS a1,"
        " COALESCE(SUM(l2), 0) AS a2,"
        " COALESCE(SUM(CASE WHEN (flags & ?) = ? AND (active_month = ? OR prev_month = ?)"
        "                   THEN l1 * ? + l2 * ? ELSE 0 END), 0) AS payable"
        " FROM (SELECT uid, MAX(flags) AS flags, MAX(active_month) AS active_month,"
        "              MAX(prev_month) AS prev_month, SUM(l1) AS l1, SUM(l2) AS l2"
        f"         FROM ({_standings_subquery()}) GROUP BY uid)",
        (COUNTABLE_MASK, COUNTABLE_VALUE, target, target, rate1, rate2, *params, *params),
    )
    if row is None:
        return {"earners": 0, "a1": 0, "a2": 0, "payable": 0.0}
    return {
        "earners": int(row["earners"]),
        "a1": int(row["a1"]),
        "a2": int(row["a2"]),
        "payable": float(row["payable"]),
    }


def active_downline_counts(month: str) -> tuple[dict[str, int], dict[str, int]]:
    """``({uid: level-1 active}, {uid: level-2 active})`` for everyone, in two queries.

    Computing this per user would mean one query per referrer — fine for a
    hundred members, hopeless for millions. These two grouped scans replace
    the whole loop.
    """
    target = month_to_int(month)
    live = "(u.flags & ?) = ? AND (u.active_month = ? OR u.prev_month = ?)"

    level1 = {
        str(row["uid"]): int(row["n"])
        for row in query(
            "SELECT u.referred_by AS uid, COUNT(*) AS n FROM users u"
            f" WHERE u.referred_by IS NOT NULL AND u.uid <> u.referred_by AND {live}"
            " GROUP BY u.referred_by",
            (COUNTABLE_MASK, COUNTABLE_VALUE, target, target),
        )
    }
    level2 = {
        str(row["uid"]): int(row["n"])
        for row in query(
            "SELECT b.referred_by AS uid, COUNT(*) AS n"
            " FROM users u JOIN users b ON b.uid = u.referred_by"
            " WHERE b.referred_by IS NOT NULL AND u.uid <> b.referred_by"
            f" AND b.uid <> b.referred_by AND {live}"
            " GROUP BY b.referred_by",
            (COUNTABLE_MASK, COUNTABLE_VALUE, target, target),
        )
    }
    return level1, level2


def count_active_downline(uid: str, month: str) -> tuple[int, int]:
    """Exact ``(level 1, level 2)`` active counts for one user.

    The payout is computed from these, not from a displayed list, so a member
    with an enormous downline is still paid correctly while the page shows
    only the first page of names.
    """
    target = month_to_int(month)
    live = "(u.flags & ?) = ? AND (u.active_month = ? OR u.prev_month = ?)"
    params = (COUNTABLE_MASK, COUNTABLE_VALUE, target, target)

    one = int(
        scalar(
            "SELECT COUNT(*) FROM users u"
            f" WHERE u.referred_by = ? AND u.uid <> ? AND {live}",
            (uid, uid, *params),
        )
    )
    two = int(
        scalar(
            "SELECT COUNT(*) FROM users u JOIN users b ON b.uid = u.referred_by"
            f" WHERE b.referred_by = ? AND b.uid <> ? AND u.uid <> ? AND {live}",
            (uid, uid, uid, *params),
        )
    )
    return one, two


def count_downline(uid: str) -> tuple[int, int]:
    """Total ``(level 1, level 2)`` sizes, active or not."""
    one = int(
        scalar(
            "SELECT COUNT(*) FROM users WHERE referred_by = ? AND uid <> ?", (uid, uid)
        )
    )
    two = int(
        scalar(
            "SELECT COUNT(*) FROM users u JOIN users b ON b.uid = u.referred_by"
            " WHERE b.referred_by = ? AND b.uid <> ? AND u.uid <> ?",
            (uid, uid, uid),
        )
    )
    return one, two


# --------------------------------------------------------------------------- #
# membership — two bits, not a table
# --------------------------------------------------------------------------- #

def set_membership(user_id: int, chat_id: int, joined: bool) -> bool:
    """Record a join or departure for one of the user's two chats.

    A user belongs to exactly one pair, so the only memberships that can
    matter are their own group and their own channel. Anything else is
    ignored, and if they are not placed yet, joining a paired chat places
    them.
    """
    user = get_user(user_id)
    if user is None:
        return False

    pair = get_pair(int(user["pair_id"])) if user["pair_id"] else None
    if pair is None or chat_id not in (pair["group_chat_id"], pair["channel_chat_id"]):
        pair = pair_for_chat(chat_id)
        if pair is None:
            return False
        if joined and not user["pair_id"]:
            assign_pair(user_id, int(pair["pair_id"]))
        elif int(user["pair_id"] or 0) != int(pair["pair_id"]):
            return False

    flag = F_IN_GROUP if chat_id == pair["group_chat_id"] else F_IN_CHANNEL
    set_flag(user_id, flag, joined)
    return True


def pair_for_chat(chat_id: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM pairs WHERE group_chat_id = ? OR channel_chat_id = ?",
        (chat_id, chat_id),
    )


def assign_pair(user_id: int, pair_id: int) -> None:
    with connect(write=True) as conn:
        row = conn.execute("SELECT pair_id FROM users WHERE id = ?", (user_id,)).fetchone()
        old = int(row["pair_id"]) if row and row["pair_id"] else None
        if old == pair_id:
            return
        conn.execute("UPDATE users SET pair_id = ? WHERE id = ?", (pair_id, user_id))
        conn.execute(
            "UPDATE pairs SET member_count = member_count + 1 WHERE pair_id = ?", (pair_id,)
        )
        if old:
            conn.execute(
                "UPDATE pairs SET member_count = MAX(0, member_count - 1)"
                " WHERE pair_id = ?",
                (old,),
            )


def clear_pair(user_id: int) -> None:
    with connect(write=True) as conn:
        row = conn.execute("SELECT pair_id FROM users WHERE id = ?", (user_id,)).fetchone()
        old = int(row["pair_id"]) if row and row["pair_id"] else None
        conn.execute(
            "UPDATE users SET pair_id = NULL, flags = flags & ~? WHERE id = ?",
            (F_IN_GROUP | F_IN_CHANNEL, user_id),
        )
        if old:
            conn.execute(
                "UPDATE pairs SET member_count = MAX(0, member_count - 1)"
                " WHERE pair_id = ?",
                (old,),
            )


# --------------------------------------------------------------------------- #
# bots
# --------------------------------------------------------------------------- #

def list_bots() -> list[sqlite3.Row]:
    return query("SELECT * FROM bots ORDER BY bot_id")


def get_bot(bot_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM bots WHERE bot_id = ?", (bot_id,))


def get_bot_by_token(token: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM bots WHERE token = ?", (token,))


def add_bot(token: str, name: str, role: str, status: str = "running") -> int:
    existing = get_bot_by_token(token)
    if existing is not None:
        return int(existing["bot_id"])
    return int(
        execute(
            "INSERT INTO bots(token, name, role, status, added_at) VALUES (?, ?, ?, ?, ?)",
            (token.strip(), name.strip() or "bot", role, status, iso_utc()),
        )
    )


def update_bot(bot_id: int, **fields: Any) -> None:
    allowed = {"token", "name", "role", "status", "username", "telegram_id", "last_error"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    execute(f"UPDATE bots SET {assignments} WHERE bot_id = ?", (*updates.values(), bot_id))


def delete_bot(bot_id: int) -> None:
    with connect(write=True) as conn:
        conn.execute("DELETE FROM chats WHERE bot_id = ?", (bot_id,))
        conn.execute("DELETE FROM bots WHERE bot_id = ?", (bot_id,))


def bots_with_role(role: str, running_only: bool = True) -> list[sqlite3.Row]:
    if running_only:
        return query(
            "SELECT * FROM bots WHERE role = ? AND status = 'running' ORDER BY bot_id",
            (role,),
        )
    return query("SELECT * FROM bots WHERE role = ? ORDER BY bot_id", (role,))


# --------------------------------------------------------------------------- #
# chats & pairs
# --------------------------------------------------------------------------- #

def list_chats(bot_id: int | None = None) -> list[sqlite3.Row]:
    if bot_id is None:
        return query(
            "SELECT c.*, b.name AS bot_name, b.role AS bot_role FROM chats c"
            " LEFT JOIN bots b ON b.bot_id = c.bot_id ORDER BY c.chat_type, c.chat_id"
        )
    return query("SELECT * FROM chats WHERE bot_id = ? ORDER BY chat_type", (bot_id,))


def chat_rows(chat_id: int) -> list[sqlite3.Row]:
    """Every bot registration for one chat."""
    return query("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))


def add_chat(
    chat_id: int,
    bot_id: int,
    chat_type: str,
    title: str | None,
    pair_id: int | None = None,
) -> None:
    execute(
        "INSERT INTO chats(chat_id, bot_id, chat_type, title, pair_id, added_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(chat_id, bot_id) DO UPDATE SET"
        " chat_type = excluded.chat_type,"
        " title = COALESCE(excluded.title, chats.title),"
        " pair_id = COALESCE(excluded.pair_id, chats.pair_id)",
        (chat_id, bot_id, chat_type, title, pair_id, iso_utc()),
    )


def set_chat_pair(chat_id: int, pair_id: int | None) -> None:
    execute("UPDATE chats SET pair_id = ? WHERE chat_id = ?", (pair_id, chat_id))


def delete_chat(chat_id: int, bot_id: int) -> None:
    execute("DELETE FROM chats WHERE chat_id = ? AND bot_id = ?", (chat_id, bot_id))


def distinct_managed_chats() -> list[sqlite3.Row]:
    """One row per chat_id, with any bot that can post there."""
    return query(
        "SELECT chat_id, chat_type, MIN(bot_id) AS bot_id,"
        " MAX(title) AS title, MAX(pair_id) AS pair_id"
        " FROM chats GROUP BY chat_id, chat_type ORDER BY chat_type, chat_id"
    )


def list_pairs() -> list[sqlite3.Row]:
    return query("SELECT * FROM pairs ORDER BY pair_id")


def get_pair(pair_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM pairs WHERE pair_id = ?", (pair_id,))


def create_pair(
    title: str,
    group_chat_id: int | None,
    channel_chat_id: int | None,
    capacity: int = 0,
) -> int:
    pair_id = int(
        execute(
            "INSERT INTO pairs(title, group_chat_id, channel_chat_id, capacity, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (title, group_chat_id, channel_chat_id, capacity, iso_utc()),
        )
    )
    for chat_id in (group_chat_id, channel_chat_id):
        if chat_id:
            set_chat_pair(chat_id, pair_id)
    return pair_id


def update_pair(pair_id: int, **fields: Any) -> None:
    allowed = {"title", "group_chat_id", "channel_chat_id", "capacity", "closed"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        execute(
            f"UPDATE pairs SET {assignments} WHERE pair_id = ?",
            (*updates.values(), pair_id),
        )
    pair = get_pair(pair_id)
    if pair:
        for chat_id in (pair["group_chat_id"], pair["channel_chat_id"]):
            if chat_id:
                set_chat_pair(chat_id, pair_id)


def delete_pair(pair_id: int) -> None:
    with connect(write=True) as conn:
        conn.execute("UPDATE chats SET pair_id = NULL WHERE pair_id = ?", (pair_id,))
        conn.execute(
            "UPDATE users SET pair_id = NULL, flags = flags & ~? WHERE pair_id = ?",
            (F_IN_GROUP | F_IN_CHANNEL, pair_id),
        )
        conn.execute("DELETE FROM pairs WHERE pair_id = ?", (pair_id,))


def set_default_pair(pair_id: int) -> None:
    with connect(write=True) as conn:
        conn.execute("UPDATE pairs SET is_default = 0")
        conn.execute("UPDATE pairs SET is_default = 1 WHERE pair_id = ?", (pair_id,))


def set_primary_pair(pair_id: int) -> None:
    with connect(write=True) as conn:
        conn.execute("UPDATE pairs SET is_primary = 0")
        conn.execute("UPDATE pairs SET is_primary = 1 WHERE pair_id = ?", (pair_id,))


def default_pair() -> sqlite3.Row | None:
    return query_one("SELECT * FROM pairs WHERE is_default = 1 AND closed = 0 LIMIT 1")


def primary_pair() -> sqlite3.Row | None:
    return query_one("SELECT * FROM pairs WHERE is_primary = 1 LIMIT 1")


def recount_pairs() -> None:
    """Rebuild ``pairs.member_count`` from the users table.

    The counter is maintained incrementally; this is the repair tool for when
    it drifts (a crash mid-write, a manual SQL edit).
    """
    with connect(write=True) as conn:
        conn.execute("UPDATE pairs SET member_count = 0")
        conn.execute(
            "UPDATE pairs SET member_count = COALESCE((SELECT COUNT(*) FROM users u"
            " WHERE u.pair_id = pairs.pair_id), 0)"
        )


def usable_pairs() -> list[sqlite3.Row]:
    """Pairs that are open, complete (group + channel) and not over capacity."""
    return [
        pair
        for pair in query(
            "SELECT * FROM pairs WHERE closed = 0 AND group_chat_id IS NOT NULL"
            " AND channel_chat_id IS NOT NULL ORDER BY pair_id"
        )
        if not pair["capacity"] or pair["member_count"] < pair["capacity"]
    ]


def choose_pair(referrer_pair_id: int | None) -> sqlite3.Row | None:
    """Pick the pair a newly verified user should be placed in.

    Order: the referrer's pair, then the admin default, then the least loaded
    open pair. Returns ``None`` when no pair is configured yet.
    """
    available = usable_pairs()
    if not available:
        return None
    by_id = {int(pair["pair_id"]): pair for pair in available}

    if referrer_pair_id and int(referrer_pair_id) in by_id:
        return by_id[int(referrer_pair_id)]

    fallback = default_pair()
    if fallback is not None and int(fallback["pair_id"]) in by_id:
        return by_id[int(fallback["pair_id"])]

    return min(available, key=lambda pair: int(pair["member_count"]))


# --------------------------------------------------------------------------- #
# bank details
# --------------------------------------------------------------------------- #

def get_bank_details(user_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM bank_details WHERE user_id = ?", (user_id,))


def save_bank_details(
    user_id: int, full_name: str, account_number: str, ifsc: str, upi_id: str
) -> bool:
    """Insert bank details. Returns False if the user already submitted once.

    One account per public ID, fixed for good: there is no update path here on
    purpose, so the destination of a payout cannot be changed by whoever holds
    the Telegram account at payout time.
    """
    with connect(write=True) as conn:
        existing = conn.execute(
            "SELECT 1 FROM bank_details WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is not None:
            return False
        conn.execute(
            "INSERT INTO bank_details(user_id, full_name, account_number, ifsc, upi_id,"
            " submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, full_name, account_number, ifsc.upper(), upi_id, epoch()),
        )
        return True


def list_bank_details(limit: int = 500) -> list[sqlite3.Row]:
    return query(
        "SELECT b.*, u.uid FROM bank_details b"
        " LEFT JOIN users u ON u.id = b.user_id ORDER BY b.submitted_at DESC LIMIT ?",
        (limit,),
    )


def count_bank_details() -> int:
    return int(scalar("SELECT COUNT(*) FROM bank_details"))


def users_without_bank_details(limit: int = 5000) -> list[sqlite3.Row]:
    """Verified users who still owe bank details, newest first.

    Bounded on purpose: the daily DM sweep can only reach a few thousand
    people a day at Telegram's rate limits, so loading millions would be
    pointless as well as expensive.
    """
    return query(
        "SELECT u.* FROM users u LEFT JOIN bank_details b ON b.user_id = u.id"
        " WHERE b.user_id IS NULL AND (u.flags & ?) = ? AND (u.flags & ?) = 0"
        " ORDER BY u.joined_at DESC LIMIT ?",
        (F_VERIFIED, F_VERIFIED, F_DUPLICATE | F_BANNED, limit),
    )


# --------------------------------------------------------------------------- #
# withdrawals
# --------------------------------------------------------------------------- #

def get_withdrawal(user_id: int, month: str) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?",
        (user_id, month_to_int(month)),
    )


def create_withdrawal(user_id: int, month: str, amount: float) -> sqlite3.Row | None:
    month_i = month_to_int(month)
    with connect(write=True) as conn:
        existing = conn.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?", (user_id, month_i)
        ).fetchone()
        if existing is not None:
            return None
        try:
            conn.execute(
                "INSERT INTO withdrawals(user_id, month, amount, status, created_at)"
                " VALUES (?, ?, ?, 'pending', ?)",
                (user_id, month_i, amount, epoch()),
            )
        except sqlite3.IntegrityError:
            return None  # two requests raced; UNIQUE(user_id, month) settled it
        return conn.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?", (user_id, month_i)
        ).fetchone()


def set_withdrawal_status(withdrawal_id: int, status: str, note: str = "") -> None:
    execute(
        "UPDATE withdrawals SET status = ?, processed_at = ?, note = ? WHERE id = ?",
        (status, epoch(), note or None, withdrawal_id),
    )


def list_withdrawals(month: str | None = None, status: str | None = None) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if month:
        clauses.append("w.month = ?")
        params.append(month_to_int(month))
    if status and status != "all":
        clauses.append("w.status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return query(
        "SELECT w.*, u.uid, b.full_name, b.account_number, b.ifsc, b.upi_id"
        " FROM withdrawals w"
        " LEFT JOIN users u ON u.id = w.user_id"
        " LEFT JOIN bank_details b ON b.user_id = w.user_id"
        f"{where} ORDER BY w.created_at DESC",
        params,
    )


def withdrawal_months() -> list[str]:
    from app.timeutil import month_from_int

    months = [
        month_from_int(int(row["month"]))
        for row in query("SELECT DISTINCT month FROM withdrawals ORDER BY month DESC")
    ]
    if current_month() not in months:
        months.insert(0, current_month())
    return months


# --------------------------------------------------------------------------- #
# moderation
# --------------------------------------------------------------------------- #

def add_warning(user_id: int, chat_id: int) -> int:
    with connect(write=True) as conn:
        conn.execute(
            "INSERT INTO warnings(user_id, chat_id, count, updated_at) VALUES (?, ?, 1, ?)"
            " ON CONFLICT(user_id, chat_id) DO UPDATE SET"
            " count = warnings.count + 1, updated_at = excluded.updated_at",
            (user_id, chat_id, epoch()),
        )
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        return int(row["count"]) if row else 1


def reset_warnings(user_id: int, chat_id: int | None = None) -> None:
    if chat_id is None:
        execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
    else:
        execute("DELETE FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))


def warning_count(user_id: int, chat_id: int) -> int:
    return int(
        scalar(
            "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
    )


# Below this many members every aggregate is fast enough to run live, so the
# panel always shows the truth. Above it, the whole-table scans behind the
# leaderboard and the dashboard totals are served from a snapshot the daily
# job refreshes, because a leaderboard does not need to be real-time and a
# hundred-second page load does.
LIVE_AGGREGATE_LIMIT = 20_000


def user_count() -> int:
    """Total members, O(1).

    ``SELECT COUNT(*)`` scans the table, so the count is maintained as a
    counter and repaired by :func:`recount_users`.
    """
    stored = get_setting("user_count", "")
    if stored.isdigit():
        return int(stored)
    return recount_users()


def recount_users() -> int:
    total = int(scalar("SELECT COUNT(*) FROM users"))
    set_setting("user_count", str(total))
    return total


def aggregates_are_live() -> bool:
    return user_count() <= LIVE_AGGREGATE_LIMIT


def cached_snapshot(key: str, compute, max_age: int = 86_400) -> tuple[Any, int]:
    """Serve ``compute()`` from a stored snapshot. Returns ``(value, taken_at)``.

    Small installs never get here — :func:`aggregates_are_live` sends them
    down the live path — so the staleness only applies where the live query
    would be too slow to serve anyway.
    """
    raw = get_setting(key, "")
    taken = get_setting_int(f"{key}_at", 0)
    if raw and (epoch() - taken) < max_age:
        try:
            return json.loads(raw), taken
        except json.JSONDecodeError:
            pass
    value = compute()
    now = epoch()
    set_setting(key, json.dumps(value))
    set_setting(f"{key}_at", str(now))
    return value, now


def refresh_snapshots() -> None:
    """Recompute the cached aggregates. Called by the daily job."""
    from app import earnings

    recount_users()
    cached_snapshot("stats_cache", compute_stats, max_age=0)
    month = current_month()
    cached_snapshot(
        "totals_cache", lambda: earnings.compute_month_totals(month), max_age=0
    )
    cached_snapshot("board_cache", lambda: earnings.compute_board(month), max_age=0)


def db_size_bytes() -> int:
    path = Path(settings.db_path)
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            total += candidate.stat().st_size
    return total


def compute_stats() -> dict[str, Any]:
    """The real counts. Whole-table scans, so callers go through stats()."""
    users = user_count()
    size = db_size_bytes()
    return {
        "users": users,
        "verified": count_users("(flags & ?) = ?", (F_VERIFIED, F_VERIFIED)),
        "unverified": count_users("(flags & ?) = 0", (F_VERIFIED,)),
        "duplicates": count_users("(flags & ?) <> 0", (F_DUPLICATE,)),
        "banned": count_users("(flags & ?) <> 0", (F_BANNED,)),
        "bots": int(scalar("SELECT COUNT(*) FROM bots")),
        "bots_running": int(scalar("SELECT COUNT(*) FROM bots WHERE status = 'running'")),
        "chats": int(scalar("SELECT COUNT(DISTINCT chat_id) FROM chats")),
        "pairs": int(scalar("SELECT COUNT(*) FROM pairs")),
        "bank_details": count_bank_details(),
        "activity_this_month": active_user_count(),
        "pending_withdrawals": int(
            scalar("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        ),
        "db_bytes": size,
        "bytes_per_user": round(size / users) if users else 0,
    }


def stats() -> dict[str, Any]:
    """Dashboard counts — live when that is cheap, snapshotted when it is not."""
    if aggregates_are_live():
        return compute_stats()
    value, taken = cached_snapshot("stats_cache", compute_stats)
    value["snapshot_at"] = taken
    return value

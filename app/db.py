"""SQLite access layer.

Design notes
------------
* One connection per operation, handed out by the :func:`connect` context
  manager. WAL mode lets the FastAPI request handlers and the bot polling
  tasks read concurrently while a single writer commits.
* ``users.id`` is the *Telegram user id*. Telegram ids are global, so every
  bot in the fleet sees the same id for the same person and all foreign keys
  (memberships, activity, bank details) line up without a mapping table.
* All queries are parameterised. The only string interpolation is over
  column/table names that this module itself controls.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app.config import settings
from app.ids import random_uid
from app.timeutil import current_month, iso_utc, month_key

# SQLite serialises writers itself, but a process-wide lock keeps the
# "read, decide, write" sequences in this module atomic against each other.
_write_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,          -- Telegram user id
    uid             TEXT UNIQUE NOT NULL,
    username        TEXT,
    full_name       TEXT,
    phone_hash      TEXT UNIQUE,
    referred_by_uid TEXT,
    verified        INTEGER NOT NULL DEFAULT 0,
    duplicate       INTEGER NOT NULL DEFAULT 0,
    banned          INTEGER NOT NULL DEFAULT 0,
    pair_id         INTEGER,
    joined_at       TEXT NOT NULL,
    last_seen       TEXT,
    message_count   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by_uid);
CREATE INDEX IF NOT EXISTS idx_users_pair ON users(pair_id);

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
CREATE INDEX IF NOT EXISTS idx_chats_pair ON chats(pair_id);

CREATE TABLE IF NOT EXISTS pairs (
    pair_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    group_chat_id   INTEGER,
    channel_chat_id INTEGER,
    is_default      INTEGER NOT NULL DEFAULT 0,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    capacity        INTEGER NOT NULL DEFAULT 0,   -- 0 = unlimited
    closed          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    chat_type TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT,
    left_at   TEXT,
    PRIMARY KEY (user_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_chat ON memberships(chat_id, status);

CREATE TABLE IF NOT EXISTS user_activity (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    month         TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    payload       TEXT,
    ts            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_user_month ON user_activity(user_id, month);
CREATE INDEX IF NOT EXISTS idx_activity_month ON user_activity(month);

CREATE TABLE IF NOT EXISTS invite_links (
    user_id      INTEGER NOT NULL,
    chat_id      INTEGER NOT NULL,
    invite_link  TEXT NOT NULL,
    link_name    TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_invite_name ON invite_links(link_name);

CREATE TABLE IF NOT EXISTS bank_details (
    user_id        INTEGER PRIMARY KEY,
    full_name      TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc           TEXT NOT NULL,
    upi_id         TEXT NOT NULL,
    submitted_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    month        TEXT NOT NULL,
    amount       REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    processed_at TEXT,
    note         TEXT,
    UNIQUE (user_id, month)
);
CREATE INDEX IF NOT EXISTS idx_withdrawals_month ON withdrawals(month, status);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    user_id    INTEGER,
    event_type TEXT NOT NULL,
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS warnings (
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "daily_prompt_text": (
        "💳 <b>Daily reminder</b>\n\n"
        "Payouts go out by bank transfer once a month. If you have not "
        "submitted your bank details yet, open the main bot and send /bank — "
        "it asks for your name, account number, IFSC and UPI id one at a time."
    ),
    "daily_prompt_dm": "1",
    "broadcast_confirm": "1",
    "moderation_enabled": "1",
    "flood_limit": "6",
    "flood_window_seconds": "8",
    "warn_mute_at": "3",
    "warn_ban_at": "5",
    "mute_minutes": "60",
    "block_links_from_unverified": "1",
    "banned_words": "",
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
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")


@contextmanager
def connect(write: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a connection for the duration of one operation.

    ``write=True`` also takes the process-wide write lock and commits on a
    clean exit, so a caller can do read-modify-write without racing another
    bot task or web request.
    """
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


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    """Create the schema and backfill columns added after a deploy."""
    with connect(write=True) as conn:
        conn.executescript(SCHEMA)
        # Forward-compatible column adds for databases created by older builds.
        additions = {
            "users": {
                "full_name": "TEXT",
                "banned": "INTEGER NOT NULL DEFAULT 0",
                "message_count": "INTEGER NOT NULL DEFAULT 0",
            },
            "bots": {
                "role": "TEXT NOT NULL DEFAULT 'main'",
                "username": "TEXT",
                "telegram_id": "INTEGER",
                "last_error": "TEXT",
            },
            "pairs": {
                "title": "TEXT",
                "capacity": "INTEGER NOT NULL DEFAULT 0",
                "closed": "INTEGER NOT NULL DEFAULT 0",
            },
            "withdrawals": {"note": "TEXT"},
        }
        for table, columns in additions.items():
            have = _existing_columns(conn, table)
            for column, decl in columns.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )


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
        (iso_utc(), user_id, event_type, payload),
    )


def recent_events(limit: int = 200, user_id: int | None = None) -> list[sqlite3.Row]:
    if user_id is not None:
        return query(
            "SELECT * FROM events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
    return query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #

def get_user(user_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_uid(uid: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE uid = ?", (uid,))


def get_user_by_phone_hash(phone_hash: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM users WHERE phone_hash = ?", (phone_hash,))


def create_user(
    user_id: int,
    username: str | None,
    full_name: str | None,
    referred_by_uid: str | None,
) -> sqlite3.Row:
    """Insert a user with a collision-safe UID, or return the existing row.

    ``/start`` is idempotent: a repeat call never creates a second row and
    never rewrites an existing referrer.
    """
    with connect(write=True) as conn:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE users SET username = ?, full_name = ?, last_seen = ? WHERE id = ?",
                (username, full_name, iso_utc(), user_id),
            )
            if existing["referred_by_uid"] is None and referred_by_uid:
                conn.execute(
                    "UPDATE users SET referred_by_uid = ? WHERE id = ?",
                    (referred_by_uid, user_id),
                )
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        now = iso_utc()
        for _ in range(25):  # retry on the (astronomically rare) UID collision
            uid = random_uid()
            try:
                conn.execute(
                    "INSERT INTO users(id, uid, username, full_name, referred_by_uid,"
                    " joined_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, uid, username, full_name, referred_by_uid, now, now),
                )
                break
            except sqlite3.IntegrityError as exc:
                if "users.uid" not in str(exc):
                    raise
        else:
            raise RuntimeError("could not allocate a unique UID after 25 attempts")
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def touch_user(user_id: int, username: str | None = None, full_name: str | None = None) -> None:
    with connect(write=True) as conn:
        if username is None and full_name is None:
            conn.execute("UPDATE users SET last_seen = ? WHERE id = ?", (iso_utc(), user_id))
        else:
            conn.execute(
                "UPDATE users SET last_seen = ?,"
                " username = COALESCE(?, username), full_name = COALESCE(?, full_name)"
                " WHERE id = ?",
                (iso_utc(), username, full_name, user_id),
            )


def set_user_fields(user_id: int, **fields: Any) -> None:
    allowed = {
        "username",
        "full_name",
        "phone_hash",
        "referred_by_uid",
        "verified",
        "duplicate",
        "banned",
        "pair_id",
        "last_seen",
        "message_count",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    execute(
        f"UPDATE users SET {assignments} WHERE id = ?",
        (*updates.values(), user_id),
    )


def bump_message_count(user_id: int) -> None:
    execute(
        "UPDATE users SET message_count = message_count + 1, last_seen = ? WHERE id = ?",
        (iso_utc(), user_id),
    )


def count_users(where: str = "", params: Sequence[Any] = ()) -> int:
    clause = f" WHERE {where}" if where else ""
    return int(scalar(f"SELECT COUNT(*) FROM users{clause}", params))


def list_users(
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[sqlite3.Row]:
    if search:
        like = f"%{search.strip()}%"
        return query(
            "SELECT * FROM users WHERE uid LIKE ? OR username LIKE ? OR full_name LIKE ?"
            " OR CAST(id AS TEXT) LIKE ? ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (like, like, like, like, limit, offset),
        )
    return query(
        "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?", (limit, offset)
    )


def referrals_of(uid: str) -> list[sqlite3.Row]:
    return query(
        "SELECT * FROM users WHERE referred_by_uid = ? ORDER BY joined_at DESC", (uid,)
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


def get_chat(chat_id: int, bot_id: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM chats WHERE chat_id = ? AND bot_id = ?", (chat_id, bot_id)
    )


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
    """One row per chat_id, with any bot that can post there.

    Broadcasting must hit each chat exactly once even when three bots are
    admins in it.
    """
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
        conn.execute("UPDATE users SET pair_id = NULL WHERE pair_id = ?", (pair_id,))
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


def pair_load() -> dict[int, int]:
    rows = query("SELECT pair_id, COUNT(*) AS n FROM users WHERE pair_id IS NOT NULL GROUP BY pair_id")
    return {int(row["pair_id"]): int(row["n"]) for row in rows}


def usable_pairs() -> list[sqlite3.Row]:
    """Pairs that are open, complete (group + channel) and not over capacity."""
    load = pair_load()
    out = []
    for pair in query(
        "SELECT * FROM pairs WHERE closed = 0 AND group_chat_id IS NOT NULL"
        " AND channel_chat_id IS NOT NULL ORDER BY pair_id"
    ):
        capacity = int(pair["capacity"] or 0)
        if capacity and load.get(int(pair["pair_id"]), 0) >= capacity:
            continue
        out.append(pair)
    return out


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

    load = pair_load()
    return min(available, key=lambda pair: load.get(int(pair["pair_id"]), 0))


# --------------------------------------------------------------------------- #
# memberships
# --------------------------------------------------------------------------- #

def set_membership(
    user_id: int,
    chat_id: int,
    chat_type: str,
    status: str,
) -> None:
    """Record a membership transition.

    A rejoin writes a fresh ``joined_at`` and clears ``left_at``; a departure
    stamps ``left_at`` and keeps the row so history is not lost.
    """
    now = iso_utc()
    joined_at = now if status == "member" else None
    left_at = None if status == "member" else now
    with connect(write=True) as conn:
        row = conn.execute(
            "SELECT status FROM memberships WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO memberships(user_id, chat_id, chat_type, status, joined_at, left_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, chat_id, chat_type, status, joined_at, left_at),
            )
        elif status == "member":
            conn.execute(
                "UPDATE memberships SET status = 'member', chat_type = ?, joined_at = ?,"
                " left_at = NULL WHERE user_id = ? AND chat_id = ?",
                (chat_type, now, user_id, chat_id),
            )
        else:
            conn.execute(
                "UPDATE memberships SET status = ?, chat_type = ?, left_at = ?"
                " WHERE user_id = ? AND chat_id = ?",
                (status, chat_type, now, user_id, chat_id),
            )


def get_membership(user_id: int, chat_id: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM memberships WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)
    )


def is_member(user_id: int, chat_id: int | None) -> bool:
    if not chat_id:
        return False
    row = get_membership(user_id, int(chat_id))
    return row is not None and row["status"] == "member"


def memberships_of(user_id: int) -> list[sqlite3.Row]:
    return query(
        "SELECT m.*, (SELECT MAX(title) FROM chats c WHERE c.chat_id = m.chat_id) AS title"
        " FROM memberships m WHERE m.user_id = ? ORDER BY m.chat_type",
        (user_id,),
    )


def members_of_chat(chat_id: int) -> list[int]:
    return [
        int(row["user_id"])
        for row in query(
            "SELECT user_id FROM memberships WHERE chat_id = ? AND status = 'member'",
            (chat_id,),
        )
    ]


# --------------------------------------------------------------------------- #
# invite links
# --------------------------------------------------------------------------- #

def save_invite_link(user_id: int, chat_id: int, link: str, name: str) -> None:
    execute(
        "INSERT INTO invite_links(user_id, chat_id, invite_link, link_name, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id, chat_id) DO UPDATE SET"
        " invite_link = excluded.invite_link, link_name = excluded.link_name,"
        " created_at = excluded.created_at",
        (user_id, chat_id, link, name, iso_utc()),
    )


def get_invite_link(user_id: int, chat_id: int) -> str | None:
    row = query_one(
        "SELECT invite_link FROM invite_links WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    return row["invite_link"] if row else None


def owner_of_invite_link(link: str | None, name: str | None) -> sqlite3.Row | None:
    """Resolve who a named invite link belongs to, by URL first then by name."""
    if link:
        row = query_one(
            "SELECT u.* FROM invite_links i JOIN users u ON u.id = i.user_id"
            " WHERE i.invite_link = ? LIMIT 1",
            (link,),
        )
        if row is not None:
            return row
    if name:
        return query_one("SELECT * FROM users WHERE uid = ? LIMIT 1", (name.strip().upper(),))
    return None


# --------------------------------------------------------------------------- #
# activity
# --------------------------------------------------------------------------- #

def record_activity(
    user_id: int,
    activity_type: str,
    payload: str = "",
    once_per_day: bool = False,
) -> None:
    """Append a row to ``user_activity``.

    ``once_per_day`` collapses high-volume signals (group chatter) to a single
    row per user per type per IST day. It changes nothing about eligibility —
    one interaction in the month is all that is ever required — it only keeps
    the table from growing without bound.
    """
    now = iso_utc()
    month = month_key(now)
    with connect(write=True) as conn:
        if once_per_day:
            day = now[:10]
            existing = conn.execute(
                "SELECT 1 FROM user_activity WHERE user_id = ? AND activity_type = ?"
                " AND ts >= ? LIMIT 1",
                (user_id, activity_type, f"{day}T00:00:00Z"),
            ).fetchone()
            if existing is not None:
                return
        conn.execute(
            "INSERT INTO user_activity(user_id, month, activity_type, payload, ts)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, month, activity_type, payload[:500], now),
        )


def activity_count(user_id: int, month: str) -> int:
    return int(
        scalar(
            "SELECT COUNT(*) FROM user_activity WHERE user_id = ? AND month = ?",
            (user_id, month),
        )
    )


def has_activity(user_id: int, month: str) -> bool:
    return (
        query_one(
            "SELECT 1 FROM user_activity WHERE user_id = ? AND month = ? LIMIT 1",
            (user_id, month),
        )
        is not None
    )


def activity_rows(
    user_id: int | None = None,
    month: str | None = None,
    activity_type: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("a.user_id = ?")
        params.append(user_id)
    if month:
        clauses.append("a.month = ?")
        params.append(month)
    if activity_type:
        clauses.append("a.activity_type = ?")
        params.append(activity_type)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return query(
        "SELECT a.*, u.uid, u.username FROM user_activity a"
        f" LEFT JOIN users u ON u.id = a.user_id{where} ORDER BY a.id DESC LIMIT ?",
        params,
    )


def activity_counts_for_month(month: str) -> dict[int, int]:
    rows = query(
        "SELECT user_id, COUNT(*) AS n FROM user_activity WHERE month = ? GROUP BY user_id",
        (month,),
    )
    return {int(row["user_id"]): int(row["n"]) for row in rows}


# --------------------------------------------------------------------------- #
# bank details
# --------------------------------------------------------------------------- #

def get_bank_details(user_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM bank_details WHERE user_id = ?", (user_id,))


def save_bank_details(
    user_id: int, full_name: str, account_number: str, ifsc: str, upi_id: str
) -> bool:
    """Insert bank details. Returns False if the user already submitted once."""
    with connect(write=True) as conn:
        existing = conn.execute(
            "SELECT 1 FROM bank_details WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is not None:
            return False
        conn.execute(
            "INSERT INTO bank_details(user_id, full_name, account_number, ifsc, upi_id,"
            " submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, full_name, account_number, ifsc.upper(), upi_id, iso_utc()),
        )
        return True


def list_bank_details(limit: int = 500) -> list[sqlite3.Row]:
    return query(
        "SELECT b.*, u.uid, u.username FROM bank_details b"
        " LEFT JOIN users u ON u.id = b.user_id ORDER BY b.submitted_at DESC LIMIT ?",
        (limit,),
    )


def users_without_bank_details() -> list[sqlite3.Row]:
    return query(
        "SELECT u.* FROM users u LEFT JOIN bank_details b ON b.user_id = u.id"
        " WHERE b.user_id IS NULL AND u.verified = 1 AND u.duplicate = 0 AND u.banned = 0"
    )


# --------------------------------------------------------------------------- #
# withdrawals
# --------------------------------------------------------------------------- #

def get_withdrawal(user_id: int, month: str) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?", (user_id, month)
    )


def create_withdrawal(user_id: int, month: str, amount: float) -> sqlite3.Row | None:
    with connect(write=True) as conn:
        existing = conn.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?", (user_id, month)
        ).fetchone()
        if existing is not None:
            return None
        conn.execute(
            "INSERT INTO withdrawals(user_id, month, amount, status, created_at)"
            " VALUES (?, ?, ?, 'pending', ?)",
            (user_id, month, amount, iso_utc()),
        )
        return conn.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? AND month = ?", (user_id, month)
        ).fetchone()


def set_withdrawal_status(withdrawal_id: int, status: str, note: str = "") -> None:
    execute(
        "UPDATE withdrawals SET status = ?, processed_at = ?, note = ? WHERE id = ?",
        (status, iso_utc(), note or None, withdrawal_id),
    )


def list_withdrawals(month: str | None = None, status: str | None = None) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if month:
        clauses.append("w.month = ?")
        params.append(month)
    if status and status != "all":
        clauses.append("w.status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return query(
        "SELECT w.*, u.uid, u.username, b.full_name, b.account_number, b.ifsc, b.upi_id"
        " FROM withdrawals w"
        " LEFT JOIN users u ON u.id = w.user_id"
        " LEFT JOIN bank_details b ON b.user_id = w.user_id"
        f"{where} ORDER BY w.created_at DESC",
        params,
    )


def withdrawal_months() -> list[str]:
    rows = query("SELECT DISTINCT month FROM withdrawals ORDER BY month DESC")
    months = [row["month"] for row in rows]
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
            (user_id, chat_id, iso_utc()),
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


def stats() -> dict[str, Any]:
    return {
        "users": count_users(),
        "verified": count_users("verified = 1 AND duplicate = 0"),
        "unverified": count_users("verified = 0"),
        "duplicates": count_users("duplicate = 1"),
        "banned": count_users("banned = 1"),
        "bots": int(scalar("SELECT COUNT(*) FROM bots")),
        "bots_running": int(scalar("SELECT COUNT(*) FROM bots WHERE status = 'running'")),
        "chats": int(scalar("SELECT COUNT(DISTINCT chat_id) FROM chats")),
        "pairs": int(scalar("SELECT COUNT(*) FROM pairs")),
        "bank_details": int(scalar("SELECT COUNT(*) FROM bank_details")),
        "activity_this_month": int(
            scalar(
                "SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE month = ?",
                (current_month(),),
            )
        ),
        "pending_withdrawals": int(
            scalar("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        ),
    }


def iter_all(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]

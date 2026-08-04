"""Test fixtures.

The environment is configured before ``app`` is imported, because
``app.config`` snapshots the environment at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="referral-tests-"))
os.environ.setdefault("DB_PATH", str(TMP / "test.db"))
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("ADMIN_IDS", "999001")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test")
os.environ.setdefault("BOT_TOKENS", "")

from app import db  # noqa: E402
from app.timeutil import current_month  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """A brand-new database for every test."""
    path = Path(os.environ["DB_PATH"])
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    db.init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


@pytest.fixture
def world():
    """A configured pair plus a referrer and one referred user.

    Returns ``(referrer, referred, pair)`` as fresh rows.
    """
    db.add_chat(chat_id=-100_1, bot_id=1, chat_type="group", title="Group A")
    db.add_chat(chat_id=-100_2, bot_id=1, chat_type="channel", title="Channel A")
    pair_id = db.create_pair("Set A", -100_1, -100_2)
    db.set_default_pair(pair_id)
    db.set_primary_pair(pair_id)

    referrer = db.create_user(5001)
    db.set_user_fields(5001, phone_hash=b"hash-alice-0000")
    db.set_flags(5001, verified=True)
    db.assign_pair(5001, pair_id)

    db.create_user(5002, referred_by=str(referrer["uid"]))
    db.set_user_fields(5002, phone_hash=b"hash-bob-00000")
    db.set_flags(5002, verified=True)
    db.assign_pair(5002, pair_id)

    return db.get_user(5001), db.get_user(5002), db.get_pair(pair_id)


@pytest.fixture
def month() -> str:
    return current_month()


def join_both(user_id: int) -> None:
    db.set_membership(user_id, -100_1, True)
    db.set_membership(user_id, -100_2, True)


def leave(user_id: int, chat_id: int) -> None:
    db.set_membership(user_id, chat_id, False)

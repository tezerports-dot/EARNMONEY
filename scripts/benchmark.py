#!/usr/bin/env python3
"""Measure what this schema actually costs per user.

    DB_PATH=/tmp/bench.db python3 scripts/benchmark.py 200000

Fills a throwaway database with synthetic members — half of them with a
referrer, a realistic share with bank details and payout requests, everyone
active for the month — then reports the measured bytes per user and what that
extrapolates to at 30 million.

The numbers in docs/SCALING.md come from this script. Re-run it after any
schema change; if bytes/user moves, that document is wrong.
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DB_PATH", "/tmp/referral-benchmark.db")
os.environ.setdefault("ADMIN_TOKEN", "benchmark")
os.environ.setdefault("SESSION_SECRET", "benchmark")

from app import db  # noqa: E402
from app.ids import random_uid  # noqa: E402
from app.timeutil import current_month, current_month_int  # noqa: E402

# Rough shape of a real member base.
BANK_SHARE = 0.20      # how many have submitted bank details
WITHDRAW_SHARE = 0.10  # how many request a payout in a given month
ACTIVE_SHARE = 0.60    # how many interact at all in the month


def reset() -> None:
    path = Path(os.environ["DB_PATH"])
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    db.init_db()


def seed(count: int) -> float:
    db.add_chat(chat_id=-1001, bot_id=1, chat_type="group", title="Group A")
    db.add_chat(chat_id=-1002, bot_id=1, chat_type="channel", title="Channel A")
    pair_id = db.create_pair("Set A", -1001, -1002)
    db.set_default_pair(pair_id)

    month = current_month_int()
    month_str = current_month()
    rng = random.Random(7)
    uids: list[str] = []
    seen: set[str] = set()
    started = time.time()

    with db.connect(write=True) as conn:
        for index in range(1, count + 1):
            # UID-XXXXXX is 36^6 ≈ 2.18 billion values, so collisions are
            # expected well before 30 million rows — about 200,000 of them.
            # create_user() retries against the UNIQUE index for exactly this
            # reason; the benchmark skips the round trip and dedupes in memory.
            uid = random_uid()
            while uid in seen:
                uid = random_uid()
            seen.add(uid)
            uids.append(uid)
            # Half the base arrives through someone's link.
            referrer = rng.choice(uids) if uids and rng.random() < 0.5 else None
            flags = db.F_VERIFIED | db.F_IN_GROUP | db.F_IN_CHANNEL
            active = month if rng.random() < ACTIVE_SHARE else None
            conn.execute(
                "INSERT INTO users(id, uid, referred_by, phone_hash, flags, pair_id,"
                " joined_at, active_month, group_invite, chan_invite)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    index,
                    uid,
                    referrer,
                    index.to_bytes(16, "big"),
                    flags,
                    pair_id,
                    1_780_000_000 + index,
                    active,
                    f"AbCdEfGh{index:012d}",
                    f"ZyXwVuTs{index:012d}",
                ),
            )
            if rng.random() < BANK_SHARE:
                conn.execute(
                    "INSERT INTO bank_details(user_id, full_name, account_number,"
                    " ifsc, upi_id, submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        index,
                        f"Member Number {index}",
                        f"{index:016d}",
                        "HDFC0001234",
                        f"member{index}@okhdfcbank",
                        1_780_000_000,
                    ),
                )
                if rng.random() < WITHDRAW_SHARE / BANK_SHARE:
                    conn.execute(
                        "INSERT INTO withdrawals(user_id, month, amount, status,"
                        " created_at) VALUES (?, ?, ?, 'pending', ?)",
                        (index, db.month_to_int(month_str), 20.0, 1_780_000_000),
                    )
    return time.time() - started


def report(count: int, seconds: float) -> None:
    path = Path(os.environ["DB_PATH"])
    with db.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        rows = {
            row["name"]: conn.execute(f"SELECT COUNT(*) FROM {row['name']}").fetchone()[0]
            for row in tables
        }

    size = path.stat().st_size
    per_user = size / count

    print(f"\nSeeded {count:,} users in {seconds:.1f}s "
          f"({count / seconds:,.0f} inserts/sec)\n")
    print("Row counts")
    for name, n in sorted(rows.items(), key=lambda item: -item[1]):
        if n:
            print(f"  {name:<16} {n:>12,}")
    print(f"\nDatabase file      {size / 1e6:>9.1f} MB")
    print(f"Per user           {per_user:>9.0f} bytes")
    print("\nExtrapolated")
    for target in (1_000_000, 10_000_000, 30_000_000):
        print(f"  {target:>12,} users  {per_user * target / 1e9:>7.1f} GB")

    from app import earnings

    sample = db.query_one(
        "SELECT u.* FROM users u JOIN users c ON c.referred_by = u.uid LIMIT 1"
    )
    month = current_month()

    def timed(fn) -> float:
        started = time.time()
        fn()
        return (time.time() - started) * 1000

    print("\nPer-request work (what a page view or a bot update costs)")
    for label, fn in (
        ("get_user_by_uid", lambda: db.get_user_by_uid(sample["uid"])),
        ("record_activity", lambda: db.record_activity(int(sample["id"]))),
        ("count_active_downline", lambda: db.count_active_downline(sample["uid"], month)),
        ("report_for (user page)", lambda: earnings.report_for(sample, month)),
    ):
        print(f"  {label:<28} {timed(fn):>8.1f} ms")

    print("\nDaily refresh (one background pass, not on any request path)")
    print(f"  refresh_snapshots           {timed(db.refresh_snapshots):>8.1f} ms")

    print("\nDashboard reads, served from that snapshot")
    for label, fn in (
        ("stats", db.stats),
        ("month_totals", lambda: earnings.month_totals(month)),
        ("leaderboard", lambda: earnings.leaderboard(month, limit=10)),
    ):
        elapsed = timed(fn)
        note = "" if elapsed < 50 else "  <-- still scanning; check the cache"
        print(f"  {label:<28} {elapsed:>8.1f} ms{note}")


if __name__ == "__main__":
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
    reset()
    report(total, seed(total))

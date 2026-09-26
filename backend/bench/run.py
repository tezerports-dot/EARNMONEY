"""Benchmark the paths the app hits most (CLAUDE.md §20, §30).

Seeds a referral network into a throwaway database, then measures:

* API latency (p50/p95/p99) for the dashboard, referral table, level 1 list
  and wallet, called in-process through the real FastAPI app;
* computing one snapshot for a typical and for the largest referrer;
* how many daily snapshot refreshes the worker finishes per second.

It DROPS AND RECREATES the schema of the target database, so it only runs
against a database whose name ends in ``_bench``:

    FF_BENCH_DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/ff_bench \\
        .venv/bin/python -m bench.run --users 100000

Numbers depend on the machine; docs/PERFORMANCE.md records a run and how to
turn it into capacity.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("FF_ENV", "test")
os.environ["FF_DATABASE_URL"] = os.environ.get("FF_BENCH_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/ff_bench")
os.environ["FF_REDIS_URL"] = os.environ.get("FF_BENCH_REDIS_URL", "redis://127.0.0.1:6379/14")
os.environ.setdefault("FF_PUBLIC_BASE_URL", "https://futurefashion.test")
os.environ.setdefault("FF_LOG_LEVEL", "WARNING")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import asyncpg  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app import db, ids, timeutil  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.redis_client import redis  # noqa: E402
from app.services import jobs, referrals, sessions  # noqa: E402
from app.worker import run_ready_jobs  # noqa: E402

NOW = datetime(2026, 11, 15, 6, 30, tzinfo=UTC)  # mid-campaign
REWARD_PAISE = 20000
BACKEND = Path(__file__).resolve().parent.parent


def plain_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def check_target(url: str) -> None:
    name = urlparse(plain_dsn(url)).path.lstrip("/")
    if not name.endswith("_bench"):
        sys.exit(f"Refusing to reset database {name!r}: the benchmark only runs on a database ending in _bench.")


def reset_schema_and_migrate(url: str) -> None:
    async def reset() -> None:
        conn = await asyncpg.connect(plain_dsn(url))
        try:
            await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            await conn.close()

    asyncio.run(reset())
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


# --- Seeding --------------------------------------------------------------------


class Network:
    """A referral forest shaped like real sharing: most people invite a few
    friends, early joiners invite more, and one creator invites thousands."""

    def __init__(self, users: int, seed: int) -> None:
        rng = random.Random(seed)
        self.users = users
        self.referrer: list[int | None] = [None] * (users + 1)  # 1-based
        self.active = [False] * (users + 1)
        roots = max(1, users // 50)
        for i in range(1, users + 1):
            self.active[i] = rng.random() < 0.9
            if i <= roots:
                continue
            if rng.random() < 0.02:
                self.referrer[i] = 1  # the big creator
            else:
                self.referrer[i] = 1 + int((i - 1) * rng.random() ** 2)
        self.active[1] = True
        self.created = [NOW - timedelta(days=30) + timedelta(seconds=30 * 86400 * i / users) for i in range(users + 1)]
        codes: set[str] = set()
        self.public_id = [""] * (users + 1)
        for i in range(1, users + 1):
            code = ids.new_public_id()
            while code in codes:
                code = ids.new_public_id()
            codes.add(code)
            self.public_id[i] = code

    def ancestors(self, i: int):
        level, current = 1, self.referrer[i]
        while current is not None and level <= 4:
            yield level, current
            level, current = level + 1, self.referrer[current]


async def seed(url: str, net: Network) -> dict[str, int]:
    conn = await asyncpg.connect(plain_dsn(url))
    try:
        async with conn.transaction():
            users = []
            for i in range(1, net.users + 1):
                active = net.active[i]
                created = net.created[i]
                users.append(
                    (
                        i,
                        net.public_id[i],
                        str(6_000_000_000 + i),
                        "bench-no-login",
                        "ACTIVE" if active else "PENDING_VERIFICATION",
                        net.referrer[i],
                        10_000_000 + i if active else None,
                        None if active else NOW + timedelta(hours=12),
                        created,
                        created + timedelta(minutes=6) if active else None,
                        created,
                    )
                )
            await conn.copy_records_to_table(
                "users",
                records=users,
                columns=[
                    "id",
                    "public_id",
                    "phone",
                    "password_hash",
                    "status",
                    "referrer_id",
                    "telegram_user_id",
                    "pending_expires_at",
                    "created_at",
                    "verified_at",
                    "updated_at",
                ],
            )

            edges = []
            for i in range(1, net.users + 1):
                qualified = net.active[i]
                for level, ancestor in net.ancestors(i):
                    edges.append(
                        (
                            ancestor,
                            i,
                            level,
                            "QUALIFIED" if qualified else "PENDING",
                            net.created[i],
                            net.created[i] + timedelta(minutes=6) if qualified else None,
                        )
                    )
            await conn.copy_records_to_table(
                "referral_edges",
                records=edges,
                columns=["ancestor_id", "descendant_id", "level", "status", "created_at", "qualified_at"],
            )

            # Rewards: one per verified user whose direct referrer is verified,
            # paid from a pool funded with exactly enough.
            rewarded = [i for i in range(1, net.users + 1) if net.active[i] and net.referrer[i] and net.active[net.referrer[i]]]
            system = dict(await conn.fetch("SELECT kind, id FROM ledger_accounts WHERE user_id IS NULL"))
            campaign_id = await conn.fetchval("SELECT id FROM campaigns ORDER BY id LIMIT 1")
            next_account = await conn.fetchval("SELECT max(id) FROM ledger_accounts") + 1
            pending_account: dict[int, int] = {}
            for i in rewarded:
                beneficiary = net.referrer[i]
                if beneficiary not in pending_account:
                    pending_account[beneficiary] = next_account
                    next_account += 1
            await conn.copy_records_to_table(
                "ledger_accounts",
                records=[(acc, "USER_PENDING", user, 0, NOW) for user, acc in pending_account.items()],
                columns=["id", "kind", "user_id", "balance_paise", "created_at"],
            )

            total = len(rewarded) * REWARD_PAISE
            transactions = [(1, ids.new_reference(), "FUNDING", "funding:bench", None, None, "bench", NOW - timedelta(days=31))]
            entries = [
                (1, 1, system["COMPANY_FUNDING"], -total, NOW - timedelta(days=31)),
                (2, 1, system["PROMO_POOL"], total, NOW - timedelta(days=31)),
            ]
            rewards = []
            for n, i in enumerate(rewarded, start=2):
                at = net.created[i] + timedelta(minutes=6)
                transactions.append((n, ids.new_reference(), "REFERRAL_REWARD", f"reward:{i}:1", "user", i, "system", at))
                entries.append((2 * n - 1, n, system["PROMO_POOL"], -REWARD_PAISE, at))
                entries.append((2 * n, n, pending_account[net.referrer[i]], REWARD_PAISE, at))
                rewards.append((n - 1, net.referrer[i], i, 1, REWARD_PAISE, campaign_id, "CREDITED", n, at))
            await conn.copy_records_to_table(
                "ledger_transactions",
                records=transactions,
                columns=[
                    "id",
                    "public_id",
                    "kind",
                    "idempotency_key",
                    "reference_type",
                    "reference_id",
                    "created_by",
                    "created_at",
                ],
            )
            await conn.copy_records_to_table(
                "ledger_entries",
                records=entries,
                columns=["id", "transaction_id", "account_id", "amount_paise", "created_at"],
            )
            await conn.copy_records_to_table(
                "referral_rewards",
                records=rewards,
                columns=[
                    "id",
                    "beneficiary_id",
                    "source_user_id",
                    "level",
                    "amount_paise",
                    "campaign_id",
                    "status",
                    "ledger_transaction_id",
                    "created_at",
                ],
            )
            await conn.execute(
                """
                UPDATE ledger_accounts a SET balance_paise = s.total
                FROM (SELECT account_id, sum(amount_paise) AS total FROM ledger_entries GROUP BY account_id) s
                WHERE a.id = s.account_id
                """
            )
            await conn.execute(
                "UPDATE membership_counter SET verified_count = $1 WHERE id = 1", sum(net.active[1 : net.users + 1])
            )
            for table in ("users", "ledger_accounts", "ledger_transactions", "ledger_entries", "referral_rewards"):
                # Fixed table names, not input.
                await conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")  # noqa: S608
        await conn.execute("VACUUM ANALYZE")
        return {"users": net.users, "referral_edges": len(edges), "rewards": len(rewarded), "ledger_entries": len(entries)}
    finally:
        await conn.close()


# --- Measuring ------------------------------------------------------------------


def percentiles(samples: list[float]) -> str:
    ordered = sorted(samples)

    def pick(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))] * 1000

    return f"p50 {pick(0.50):6.1f} ms · p95 {pick(0.95):6.1f} ms · p99 {pick(0.99):6.1f} ms"


async def tokens_for(user_ids: list[int]) -> dict[int, str]:
    out = {}
    async with db.sessionmaker()() as s, s.begin():
        for user in (await s.execute(select(User).where(User.id.in_(user_ids)))).scalars():
            out[user.id] = (await sessions.issue(s, user, "bench")).access_token
    return out


async def measure_api(net: Network, requests: int, rng: random.Random) -> list[tuple[str, str]]:
    active = [i for i in range(1, net.users + 1) if net.active[i]]
    sample = rng.sample(active, min(len(active), max(50, requests // 8)))
    sample[0] = 1  # always include the biggest referrer
    tokens = await tokens_for(sample)
    results = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://bench") as client:
        headers = {"X-App-Version": "1.0.0"}
        for path in ("/v1/dashboard", "/v1/referrals/summary", "/v1/referrals/direct?limit=20", "/v1/wallet"):
            for user_id in sample:  # warm-up: first summaries compute a snapshot
                await client.get(path, headers={**headers, "Authorization": f"Bearer {tokens[user_id]}"})
            await redis().flushdb()  # the warm-up counted against per-user read limits
            samples = []
            for n in range(requests):
                user_id = sample[n % len(sample)]
                started = time.perf_counter()
                r = await client.get(path, headers={**headers, "Authorization": f"Bearer {tokens[user_id]}"})
                samples.append(time.perf_counter() - started)
                if r.status_code != 200:
                    raise SystemExit(f"{path} returned {r.status_code}: {r.text[:200]}")
            await redis().flushdb()
            results.append((f"GET {path.split('?')[0]}", percentiles(samples)))
        heavy = {**headers, "Authorization": f"Bearer {tokens[1]}"}
        samples = []
        for _ in range(50):
            started = time.perf_counter()
            await client.get("/v1/referrals/direct?limit=20", headers=heavy)
            samples.append(time.perf_counter() - started)
        results.append(("GET /v1/referrals/direct (largest referrer)", percentiles(samples)))
    return results


async def measure_snapshots(net: Network) -> list[tuple[str, str]]:
    level_one = [0] * (net.users + 1)
    for i in range(1, net.users + 1):
        if net.referrer[i]:
            level_one[net.referrer[i]] += 1
    referrers = sorted((i for i in range(2, net.users + 1) if level_one[i]), key=lambda i: level_one[i])
    typical = referrers[len(referrers) // 2]
    results = []
    for label, user_id in (("typical referrer", typical), ("largest referrer", 1)):
        samples = []
        for _ in range(20):
            async with db.sessionmaker()() as s, s.begin():
                started = time.perf_counter()
                snap = await referrals.compute_snapshot(s, user_id)
                samples.append(time.perf_counter() - started)
        counts = f"{snap.level_1_count:,} / {snap.level_2_count:,} / {snap.level_3_count:,} / {snap.level_4_count:,}"
        results.append((f"compute_snapshot, {label} (levels 1–4: {counts})", percentiles(samples)))
    return results


async def measure_worker(net: Network, jobs_to_run: int, concurrency: int) -> tuple[str, str]:
    timeutil.freeze(NOW + timedelta(days=1))
    day = timeutil.ist_date().isoformat()
    async with db.sessionmaker()() as s, s.begin():
        for user_id in range(1, min(jobs_to_run, net.users) + 1):
            await jobs.enqueue(s, "snapshot_refresh", {"user_id": user_id}, dedupe_key=f"snapshot:{user_id}:{day}")
    started = time.perf_counter()
    done = 0
    while ran := await run_ready_jobs(concurrency):
        done += ran
    elapsed = time.perf_counter() - started
    async with db.sessionmaker()() as s, s.begin():
        failed = (await s.execute(text("SELECT count(*) FROM jobs WHERE status <> 'DONE'"))).scalar_one()
    if failed:
        raise SystemExit(f"{failed} snapshot jobs did not finish")
    return (
        f"Worker: {done:,} snapshot refreshes, concurrency {concurrency}",
        f"{done / elapsed:,.0f} per second ({elapsed:.1f} s)",
    )


async def measure(url: str, net: Network, requests: int, worker_jobs: int, concurrency: int) -> list[tuple[str, str]]:
    timeutil.freeze(NOW)
    rng = random.Random(7)
    await redis().flushdb()
    try:
        results = await measure_api(net, requests, rng)
        results += await measure_snapshots(net)
        results.append(await measure_worker(net, worker_jobs, concurrency))
        return results
    finally:
        await redis().flushdb()
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--users", type=int, default=100_000)
    parser.add_argument("--requests", type=int, default=400, help="timed requests per endpoint")
    parser.add_argument("--worker-jobs", type=int, default=20_000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    url = os.environ["FF_DATABASE_URL"]
    check_target(url)
    started = time.perf_counter()
    reset_schema_and_migrate(url)
    net = Network(args.users, args.seed)
    counts = asyncio.run(seed(url, net))
    print(f"Seeded in {time.perf_counter() - started:.0f} s: " + ", ".join(f"{v:,} {k}" for k, v in counts.items()))
    results = asyncio.run(measure(url, net, args.requests, args.worker_jobs, args.concurrency))
    width = max(len(name) for name, _ in results)
    for name, value in results:
        print(f"{name.ljust(width)}  {value}")


if __name__ == "__main__":
    main()

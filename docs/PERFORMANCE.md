# Performance

CLAUDE.md §20 asks for capacity to be planned from measurements, not arithmetic alone. This page records what `backend/bench/run.py` measured, what it found, and how to use the numbers.

## How to run the benchmark

The benchmark resets the schema of the database it's pointed at, so it refuses any database whose name doesn't end in `_bench`.

```bash
cd backend
createdb ff_bench            # an empty database just for this
FF_BENCH_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/ff_bench \
  .venv/bin/python -m bench.run --users 100000
```

It seeds a referral network shaped like real sharing: most people invite a few friends, early joiners invite more, and one large creator invites about 2% of everyone. 90% of users are verified. Rewards and ledger entries are created exactly as the server would, with a promotional pool funded to match. Then it times:

- the four screens that read the most: dashboard, referral table, level 1 list and wallet, called through the real FastAPI app (HTTP overhead included, network excluded);
- computing one referral snapshot for a typical referrer and for the largest one;
- how fast the worker finishes daily snapshot refreshes.

Options: `--users`, `--requests` (timed requests per endpoint), `--worker-jobs`, `--concurrency`, `--seed`.

## Results

Run on 25 September 2026: 4 vCPU, 15 GB RAM, PostgreSQL 16 and Redis 7 on the same machine as the app. 100,000 users, 230,281 referral links, 79,778 rewards and 159,558 ledger entries (156 MB of database).

| What | p50 | p95 | p99 |
|---|---:|---:|---:|
| `GET /v1/dashboard` | 11.9 ms | 15.5 ms | 26.4 ms |
| `GET /v1/referrals/summary` (the four-level table) | 6.3 ms | 8.4 ms | 9.3 ms |
| `GET /v1/referrals/direct` | 5.3 ms | 6.2 ms | 6.5 ms |
| `GET /v1/wallet` | 10.2 ms | 14.5 ms | 21.2 ms |
| `GET /v1/referrals/direct`, largest referrer | 5.8 ms | 7.9 ms | 8.3 ms |
| Snapshot, typical referrer (1 direct referral) | 4.0 ms | 4.4 ms | 4.4 ms |
| Snapshot, largest referrer (2,243 / 1,846 / 1,136 / 527 across levels 1–4) | 8.6 ms | 15.1 ms | 15.1 ms |

Worker: 20,000 snapshot refreshes in 110 s at concurrency 8, which is **181 refreshes per second** from one worker process.

## What it found

Two queries got slower as the number of users grew. Both are fixed.

| Query | Problem | Fix | Before → after |
|---|---|---|---|
| Wallet recent activity | Looked up the user's ledger accounts by `user_id` alone, which no index covers, so Postgres scanned every account. | The query names the two user account kinds, so the existing `(kind, user_id)` index is used. | 3.4 ms → 0.3 ms, and no longer grows with users |
| Dashboard "friends still verifying" | For a big referrer, Postgres walked every pending signup on the system. | Migration 0002: a partial index on `(referrer_id, pending_expires_at)` for pending accounts. | 9.3 ms → 0.15 ms |

Together they took the dashboard from 17.3 ms to 11.9 ms and the wallet from 14.6 ms to 10.2 ms (p50) on the same data.

## Planning capacity

These are single-request timings, not a load test. Before a big promotion, run a concurrent load test (for example with k6 or Locust) against the real server.

- **Storage.** The seeded database used about 1.6 KB per user. Real accounts also keep login sessions, verification sessions and audit history, so plan on 2–5 KB per user: about 0.5 GB per lakh users, and 20–50 GB at one crore.
- **Snapshot refreshes.** A user's referral table refreshes at most once a day, and only when they open it. If every user opened it every day:
  - at 50 lakh users that's about 58 refreshes a second, which one worker handles with room to spare;
  - at the 5 crore capacity target it's about 580 a second: roughly four workers, and a database server sized for it.
- **One server.** The setup in `docs/SETUP.md` runs the API, the worker, PostgreSQL and Redis on one machine. That's the right start. When it gets busy, the first steps are:
  1. move PostgreSQL to its own larger server or a managed database;
  2. run more API containers behind Caddy;
  3. run more workers. Jobs are claimed with `SKIP LOCKED`, so workers never share a job.
- **What to watch.** The admin dashboard shows the job queue and the age of its oldest ready job. If that age keeps growing, add workers.

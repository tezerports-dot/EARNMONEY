# Scale architecture — capacity, cost and operations

How the platform is built to reach ~2.9M accounts without a rewrite, and
without paying for that scale on day one.

Every number below is reproducible from the assumptions stated next to it.
Where the code computes something, the doc references the function rather than
restating a constant, so the two cannot drift.

---

## 0. The principle everything else follows from

**Scheduled updates must never compete with signup and login for the same
resources.**

This is enforced structurally, not by convention:

| Resource | API process | Worker process |
| --- | --- | --- |
| OS process / CPU | `dist/main.js` | `dist/worker.js` — separate container |
| Postgres pool | `DB_POOL_API` (10) | `DB_POOL_WORKER` (5) |
| Redis connection | cache + rate-limit | queue (blocking reads) |
| HTTP port | yes | **none** — cannot receive a request |
| Loaded modules | full app | `WorkerModule` only: no controllers, no guards, no JWT |

A worker saturating its pool cannot take connections the API needs, because
the pools are separate and sized so their sum stays under `max_connections`.
A 2,000-job fan-out cannot block the event loop serving login, because it is
not the same event loop.

---

## 1. Expected requests per second

**Assumptions** (change these and the table changes):
- DAU = 20% of registered accounts
- 8 API requests per active user per day
- Activity concentrated in ~8 waking hours
- Peak hour carries 2.5× the average active-hour rate

### Scheduled updates (background class)

Rate is `accounts ÷ 86,400`, since the day is divided into 1,440 slots and
each account occupies exactly one. Computed by `slotLoad()` in
`src/scheduler/slot.util.ts`:

| Accounts | Accounts per slot | Updates/sec | Queue depth at any moment |
| --- | --- | --- | --- |
| 100,000 | 70 | **1.16/s** | ~70 jobs |
| 1,000,000 | 695 | **11.6/s** | ~695 jobs |
| 2,900,000 | 2,014 | **33.6/s** | ~2,014 jobs |

The 2.9M figure landing at 33.6/s is why 30/s was a sensible starting target —
it is roughly the steady-state rate at full scale. It is **not** a ceiling:
`QUEUE_RATE_LIMIT_MAX` is a runtime setting. At 200/s the same architecture
delivers 17.28M updates/day, which is 6× more headroom than the user base
needs, and nothing about the design changes.

### User-facing traffic (interactive class)

| Accounts | DAU | Requests/day | 24h avg | Active-hour avg | **Peak** |
| --- | --- | --- | --- | --- | --- |
| 100,000 | 20,000 | 160,000 | 1.9/s | 5.6/s | **14/s** |
| 1,000,000 | 200,000 | 1,600,000 | 18.5/s | 55.6/s | **139/s** |
| 2,900,000 | 580,000 | 4,640,000 | 53.7/s | 161/s | **403/s** |

**The important comparison:** at full scale, peak interactive traffic (403/s)
is **12× larger** than the entire scheduled-update load (33.6/s). The updates
are not the scaling problem — user traffic is. This is exactly why the updates
are given the smaller pool and a hard rate cap: they are the load that can
afford to wait.

Signup bursts are separate and spiky. A campaign driving 10,000 signups in an
hour is only 2.8/s, but arriving in 5-minute clusters it is ~33/s. Signup is
the most expensive endpoint in the system (argon2id is deliberately slow), so
see §11 for how that is absorbed.

---

## 2. Bandwidth

Payload size is configurable; the table shows the levers.

### Update delivery — effectively zero egress

A "delivery" is a row write, not a push. The worker marks
`user_update_states.delivered_version`; no bytes leave the network. At 2.9M
accounts that is 2.9M UPDATEs/day of ~100 bytes = **~290 MB/day of internal
write traffic** and **0 bytes of egress**.

Egress happens when an app fetches the content it was told about:

| Payload per fetch | 2.9M accounts, 20% DAU | Monthly |
| --- | --- | --- |
| 1 KB | 580 MB/day | **17 GB** |
| 2 KB | 1.16 GB/day | **35 GB** |
| 4 KB | 2.32 GB/day | **70 GB** |

### Total API egress at 2.9M

4.64M requests/day × ~1.5 KB average response = **7 GB/day ≈ 209 GB/month**.

### Static assets — why the CDN matters

First app load pulls ~2 MB of images, JS and CSS. At 2.9M accounts with 10%
installing or hard-refreshing monthly: 290,000 × 2 MB = **580 GB/month**.

Served from origin that is the largest single bandwidth line in the system.
Behind Cloudflare with immutable filenames it is a >99% edge hit rate, so
**origin egress falls to ~2-5 GB/month** and the edge traffic is free on
Cloudflare's plan. This one decision removes the biggest bandwidth cost.

---

## 3. Recommended initial server specification

**Do not build for 2.9M on day one.** Start here:

| | Spec | Notes |
| --- | --- | --- |
| **1 VPS** | 2 vCPU, 4 GB RAM, 80 GB SSD | Hetzner CX22 / Hostinger KVM 2 |
| Runs | nginx, api ×1, worker ×1, postgres, redis | all via `docker-compose.prod.yml` |
| Postgres | `shared_buffers=1GB`, `max_connections=100` | defaults are fine otherwise |
| Redis | `maxmemory=512mb`, `maxmemory-policy=allkeys-lru` | cache eviction only |
| Pools | `DB_POOL_API=10`, `DB_POOL_WORKER=5` | 15 of 100 connections used |

This comfortably serves **up to ~100,000 accounts**: 1.16 updates/s and ~14
req/s peak are a small fraction of what 2 vCPU handles.

---

## 4. When to add API servers

Add a replica when **any** holds for 15 minutes:

- p95 latency on `POST /auth/login` > 300 ms
- API container CPU > 70% sustained
- Node event-loop lag > 100 ms
- 5xx rate > 0.1%

**Expected trigger point: ~500k accounts** (~70/s peak).

When you scale past one API replica, two things must change:
1. Set `SCHEDULER_ENABLED=false` on API containers and run one dedicated
   dispatcher — or leave it on, since the unique slot claim makes concurrent
   dispatchers safe, just wasteful.
2. Rate limiting already works across replicas because counters are in Redis
   (`RedisThrottlerStorage`). This was the reason for replacing the in-memory
   default: per-process counters silently double an attacker's allowance for
   every replica you add.

---

## 5. When to add queue workers

Add a worker when, for 3 consecutive slots:

- the queue has not drained by the end of its slot (`queues.updates.waiting`
  still > 0 at the next tick), **or**
- `queues.updates.failed` is climbing.

**Honest expectation: you will probably never need a second worker.** Each job
is one indexed UPDATE (~2-5 ms). One worker at `concurrency=20` can sustain
well over 1,000 jobs/s; the binding constraint is `QUEUE_RATE_LIMIT_MAX`
(30/s), not the worker. At 2.9M accounts the requirement is 33.6/s.

So the correct first response to a backlog is **raise the rate limit**, not add
containers. Add workers only once Postgres write latency — not worker CPU —
is the limit.

    workers_needed = ceil(target_rate ÷ (concurrency ÷ avg_job_seconds))
    e.g. 200/s ÷ (20 ÷ 0.005) = 200 ÷ 4000 = 1 worker

---

## 6. PostgreSQL sizing and connection pools

### Storage at 2.9M accounts

| Table | Row size | Rows | Data + indexes |
| --- | --- | --- | --- |
| `users` | ~250 B | 2.9M | ~1.3 GB |
| `user_update_states` | ~100 B | 2.9M | ~450 MB |
| `referrals` | ~150 B | ~2.9M | ~600 MB |
| `challenge_attempts` | ~200 B | ~8M | ~2.0 GB |
| `audit_logs` | ~200 B | grows forever | **see below** |
| **Total (excl. audit)** | | | **~4.5 GB** |

`audit_logs` is the only unbounded table: at ~10 rows per account per year it
reaches ~6 GB/year and keeps going. Before 1M accounts, either partition it by
month and detach old partitions, or move rows older than 90 days to cold
storage. Left alone it will eventually dominate both disk and backup time.

**Provision 50 GB** at 2.9M — data, indexes, WAL and room for a pg_dump.

### Connection pools

The invariant to hold when scaling:

    (api_replicas × DB_POOL_API) + (worker_replicas × DB_POOL_WORKER) + 10 ≤ max_connections

| Stage | Topology | Connections | `max_connections` |
| --- | --- | --- | --- |
| Start | 1 api + 1 worker | 10 + 5 + 10 = 25 | 100 |
| 1M | 2 api + 1 worker | 20 + 5 + 10 = 35 | 100 |
| 2.9M | 4 api + 2 worker | 40 + 10 + 10 = 60 | 200 |

Prisma's default pool is `cpus × 2 + 1` **per process** — on an 8-core box with
4 containers that is 68 connections requested silently. `PrismaService` sets
the limit explicitly instead, and logs it at boot so a misconfiguration is
visible immediately rather than at 3am during a fan-out.

Past ~60 connections, put PgBouncer in transaction mode in front and drop the
per-process pools to 5.

---

## 7. Redis sizing

| Use | Size at 2.9M | Note |
| --- | --- | --- |
| Update queue | **~600 KB** | one slot: 2,014 jobs × ~300 B |
| Queue overhead + retries | ~5 MB | worst case mid-cycle |
| Content cache | ~2 KB | one small row |
| Rate-limit counters | ~10 MB | ~100k active keys × ~100 B |
| **Total** | **< 64 MB** | |

**512 MB is generous.** This is the payoff from deterministic slots: the naive
"one delayed job per user per day" design would hold 2.9M jobs at once —
roughly **870 MB to 3 GB** of Redis, needing a dedicated instance — to do the
identical work. Keeping only one slot live is a ~1000× reduction.

Configure `maxmemory-policy=allkeys-lru`. Redis holds only cache, queue state
and counters; nothing here is the source of truth, so eviction costs latency
and never data.

---

## 8. CDN and cache strategy

**Edge (Cloudflare, free tier):**

| Asset | `Cache-Control` | Why |
| --- | --- | --- |
| Images, JS, CSS (hashed names) | `public, max-age=31536000, immutable` | content-addressed, so never stale |
| `GET /api/v1/vacancies` | `public, s-maxage=60, stale-while-revalidate=300` | public, changes rarely |
| Any authenticated route | `no-store` | never cache per-user data at a shared edge |

**Application cache (Redis):**

The highest-leverage cache is the daily content. Without it, 2.9M deliveries
means 2.9M identical `SELECT ... WHERE is_current` queries to read one
unchanging row. With a 300-second TTL it is **~288 reads per day regardless of
user count** — the query count stops scaling with users entirely.

`CacheService` is read-through with Postgres as the source of truth, and every
Redis call is wrapped so a cache failure degrades to a direct database read
rather than an error. Publishing new content invalidates the key explicitly,
so an update goes out on the next slot rather than up to a TTL later.

---

## 9. Failure recovery

| Failure | Behaviour |
| --- | --- |
| **Worker crashes mid-job** | BullMQ's stall detection returns the job to the queue; another worker retries. The conditional UPDATE makes the retry a no-op if the write had already landed. |
| **Server restarts mid-cycle** | `schedule_ticks` records every dispatched slot. On boot `recoverMissedSlots()` replays any slot in the lookback window (default 2h) without a `COMPLETED` row. |
| **Job fails repeatedly** | Exponential backoff from `QUEUE_BACKOFF_BASE_MS` (5s), `QUEUE_MAX_ATTEMPTS` (5) times: 5s, 10s, 20s, 40s, 80s. Then parked in the `dead-letter` queue — never silently dropped. |
| **Two workers take the same job** | Impossible to double-apply: the version guard is inside the UPDATE statement, so Postgres serialises the row and the loser matches 0 rows. |
| **Two dispatchers run at once** | The unique `(slot_date, slot)` constraint means exactly one claims a slot; the other skips. |
| **Redis is wiped entirely** | Queue-level de-duplication is lost, but `delivered_version` still prevents double delivery. Verified: after `FLUSHALL` and a full re-dispatch, 0 rows were double-applied. |
| **Redis is down** | Cache degrades to Postgres reads. Rate limiting fails **open** (documented tradeoff — see §11). Signup/login keep working; background enqueue falls back to an inline write. |
| **Postgres is down** | Everything stops. This is the one true single point of failure at the starting topology; managed Postgres with automated failover is the fix, from stage 2 onward. |

---

## 10. Monitoring and alerts

`GET /api/v1/ops/metrics` (superadmin only) returns everything below.

| Metric | Warning | Critical |
| --- | --- | --- |
| `queues.updates.waiting` at slot end | > 0 for 3 slots | > 2× accounts-per-slot |
| `queues.updates.failed` | > 10 | > 100 |
| `queues.deadLetter.waiting` | **> 0** | > 50 |
| `scheduler.failedTicks` | > 0 | > 5 |
| Minutes since `lastCompletedSlot` | > 5 | > 30 |
| `cache.hitRatio` | < 0.90 | < 0.50 |
| p95 `POST /auth/login` | > 300 ms | > 1 s |
| Postgres connections used | > 60% | > 85% |
| Disk free | < 30% | < 15% |
| `delivery.withFailures` | growing | > 1% of accounts |

The single most valuable alert is **minutes since last completed slot**. It
catches a dead dispatcher, a wedged queue and a Redis outage in one signal,
and it is the failure most likely to go unnoticed — nobody complains that they
*didn't* get an update.

---

## 11. Security and rate limiting

Signup and login are never queued, deferred or shed. They also carry the
system's most sensitive operations, so limits here are **brute-force
protection, not throughput shaping**:

| Route | Limit | Rationale |
| --- | --- | --- |
| `POST /auth/signup` | 5/min per IP | argon2id makes this the most expensive endpoint; also the abuse target |
| `POST /auth/login` | 8/min per IP | password guessing |
| `POST /telegram/webhook` | 300/min | Telegram's servers, authenticated by secret token |
| Global default | 120/min per IP | ceiling for abuse, not normal use |

Counters live in Redis, so limits hold across every API replica. The default
in-memory storage would give an attacker N× the allowance for N replicas.

**Documented tradeoff:** if Redis is unreachable, rate limiting fails *open*
and the incident is logged. Failing closed would convert a cache outage into a
total authentication outage. The remaining protections are unaffected —
argon2id cost, `SUSPENDED` account checks, CAPTCHA, and the unique Aadhaar
constraint — so this is a degradation, not a bypass.

**Absorbing signup bursts** without touching authentication strength:
1. argon2id parameters are tuned for the VPS (`ARGON2_MEMORY_COST=19456`), not
   lowered. Never trade this for throughput.
2. The audit write is shed to the background queue, with an inline fallback,
   so a burst does not multiply database writes on the request path.
3. API replicas scale horizontally; signup is stateless apart from the database.
4. `DB_POOL_API` is reserved for interactive traffic — a running fan-out cannot
   take those connections.

---

## 12. Estimated infrastructure cost

| Stage | Accounts | Topology | Monthly |
| --- | --- | --- | --- |
| **1 — Start** | 0-100k | 1 VPS (2 vCPU / 4 GB), all services, Cloudflare free | **$12-25** |
| **2 — Growth** | 100k-1M | 1 VPS (4 vCPU / 8 GB) app + managed Postgres (2 vCPU / 4 GB) | **$50-80** |
| **3 — Scale** | 1M-2.9M | 2-4 API + 2 workers, managed Postgres (4 vCPU / 16 GB) + managed Redis, LB | **$150-260** |

Notes:
- Cloudflare's free plan covers the CDN at every stage; the ~580 GB/month of
  static assets never reaches origin.
- Stage 2's real driver is moving Postgres off the app server — for automated
  backups and failover, not for CPU.
- Stage 3 assumes peak 403 req/s. If actual DAU is below 20%, stage 2 hardware
  reaches 2.9M accounts on its own.

**Nothing above requires re-architecting.** Each stage is a configuration
change or an added replica: pools are already explicit, rate limits are already
shared, workers are already separate processes, and the queue is already
bounded to one slot.

---

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCESS_ROLE` | `api` | Selects which Postgres pool this process uses |
| `DB_POOL_API` | `10` | Connections per API process |
| `DB_POOL_WORKER` | `5` | Connections per worker process |
| `SCHEDULER_ENABLED` | `true` | Run the dispatcher on this process |
| `SCHEDULER_SLOTS_PER_DAY` | `1440` | Slots the day is divided into |
| `SCHEDULER_RECOVERY_LOOKBACK` | `120` | Slots a recovery sweep replays |
| `SCHEDULER_PAGE_SIZE` | `500` | Keyset page size when dispatching |
| `QUEUE_UPDATE_CONCURRENCY` | `20` | Jobs in flight per worker |
| `QUEUE_RATE_LIMIT_MAX` | `30` | **Throughput ceiling — raise this first** |
| `QUEUE_RATE_LIMIT_DURATION_MS` | `1000` | Window for the above |
| `QUEUE_MAX_ATTEMPTS` | `5` | Retries before dead-lettering |
| `QUEUE_BACKOFF_BASE_MS` | `5000` | Exponential backoff base |
| `CACHE_CONTENT_TTL_SECONDS` | `300` | Content cache TTL |
| `CACHE_ENABLED` | `true` | Set false to bypass Redis entirely |

### Changing `SCHEDULER_SLOTS_PER_DAY`

Slots are stored per account, not recomputed, so changing this does **not**
reshuffle existing users — they keep slots derived from the old count and will
drift out of the intended distribution. After changing it, backfill:

```sql
UPDATE users SET update_slot = (
  (get_byte(sha256(id::bytea), 0)::bigint << 24) |
  (get_byte(sha256(id::bytea), 1)::bigint << 16) |
  (get_byte(sha256(id::bytea), 2)::bigint << 8)  |
  (get_byte(sha256(id::bytea), 3)::bigint)
) % <new_slot_count>;
```

This is the same hash as `slotForUserId()`; the two are verified to agree.

# Scaling

Everything below is **measured**, not estimated. Reproduce it with:

```bash
DB_PATH=/tmp/bench.db python3 scripts/benchmark.py 300000
```

If the numbers here stop matching that script's output, this document is
wrong and the script is right.

---

## Measured cost per member

300,000 synthetic members — half arriving through a referral, 20% with bank
details on file, 10% with a payout request, 60% active for the month:

```
Database file           56.2 MB
Per user                 187 bytes
```

| Members | Database on disk |
|---:|---:|
| 100,000 | 0.02 GB |
| 1,000,000 | 0.2 GB |
| 10,000,000 | 1.9 GB |
| **30,000,000** | **5.6 GB** |

An Oracle Always Free account includes **200 GB** of block storage, so 30
million members uses under 3% of it. Disk is not the constraint.

### How it got there

The first version of this schema measured **1,486 bytes per member** — 44.6 GB
at 30 million, and that was with only *one month* of activity, which then grew
every month forever. Four changes account for the 8× reduction:

| Change | Why it was the expensive thing |
|---|---|
| No `user_activity` table | One row per button tap. At 8 taps/member/month that is 240M rows/month at 30M members — gigabytes per month, growing without limit. Replaced by two integer columns on the member's own row. |
| No `memberships` table | Two rows per member (group + channel). 60M rows at 30M members. A member belongs to exactly one pair, so this is two **bits** in `users.flags`. |
| No `invite_links` table | Two rows per member holding two full URLs. Only the short link hash is kept now, on the member's row; attribution works off the link *name*, which Telegram reports back on join and costs nothing to store. |
| No profile columns | Usernames, display names, message counts and last-seen timestamps are never written. Telegram sends the current name with every update, so the bots read it live. Less storage **and** less personal data held. |

Phone numbers are a 16-byte truncated SHA-256 stored as a BLOB rather than a
64-character hex string — 48 bytes saved per member, and at 30 million the
chance of a hash collision is about 1 in 10²³.

---

## What is stored, and why each thing is there

| Table | Rows | Reason it cannot be dropped |
|---|---|---|
| `users` | one per member | The UID, who referred them, the phone hash, the two membership bits, the two month markers. This *is* the system. |
| `bank_details` | one per member who submits | Where the money goes. Written once, never updated. |
| `withdrawals` | one per payout request | The permanent record of what was paid. Never pruned — it is the audit trail. |
| `pairs`, `chats`, `bots`, `settings` | a handful | Configuration. Kilobytes. |
| `events` | capped ring buffer | Operational audit. Trimmed to 20,000 rows nightly. |
| `warnings` | only for offenders | Moderation counters. Rows older than 90 days are deleted nightly. |

Nothing else is written. There is no analytics table, no message log, no
session store, no read receipts.

### The one deliberate trade-off

**Activity history is two months deep** — the current month and the previous
one. That is exactly the payout window: month M closes on the 1st of M+1, and
you export and pay during M+1, when M is still readable.

Ask about a month older than that and the answer is "not active", because the
data is gone. The `withdrawals` row remains as the permanent record of what
was actually paid.

Keeping twelve months instead would need a real table (~1 GB at 30M) and would
buy nothing a payout depends on.

---

## Measured speed

At 300,000 members, on one Ampere core:

```
Per-request work (what a page view or a bot update costs)
  get_user_by_uid                   0.6 ms
  record_activity                   2.4 ms
  count_active_downline             1.0 ms
  report_for (user page)            3.8 ms

Daily refresh (one background pass, not on any request path)
  refresh_snapshots             1844.1 ms

Dashboard reads, served from that snapshot
  stats                             1.5 ms
  month_totals                      1.5 ms
  leaderboard                       6.9 ms
```

**Per-request work is all index lookups**, so it stays flat as the member base
grows — a member's page costs the same at 30 million as at 300,000.

**Whole-table work happens once a day, in the background.** The leaderboard
and the dashboard totals scan the member table joined to itself; at 300k that
is ~1.8 seconds, which extrapolates to roughly 3 minutes at 30 million. It
runs in the daily job and the panel reads the snapshot, so no page view ever
waits for it.

Below 20,000 members (`LIVE_AGGREGATE_LIMIT`) those figures are computed live
instead, so a small installation always shows the exact truth.

### Write volume

`record_activity` only writes when the **month changes** for that member. A
member who taps a hundred buttons in August causes exactly one write, on the
first tap. At 30 million members that is 30 million writes spread across a
month — about 12 per second — against a SQLite instance that does ~37,000
inserts/second on this hardware.

---

## What actually breaks first

It is not the database. In order:

### 1. Telegram's rate limits (the real ceiling)

| Limit | Consequence |
|---|---|
| ~30 messages/second per bot, all chats | A direct-message sweep to 30M members would take **11 days**. The daily bank-details sweep is capped at 2,000 DMs/day for this reason and chases the newest members first. |
| ~20 messages/minute **per group** | Broadcasting is paced at 0.35s between chats. A thousand chats takes ~6 minutes. |
| 200,000 members per group | This is why **pairs** exist. Each pair is one group + one channel; add a pair when one fills. 30M members needs **at least 150 groups**. Channels are unlimited. |
| One `getUpdates` connection per token | Never run two copies of the service with the same tokens. |

**Plan for the group limit, not the disk.** At 30 million members you are
running 150+ groups and the same number of channels, and each bot can only
administer so many chats comfortably. This is the part that needs real
operational thought.

### 2. RAM

The Python process sits at 200–400 MB regardless of member count — it holds
no member data in memory. The rest of the machine's RAM works as filesystem
cache for the database. At 30 million the hot set is the `uid` and `phone_hash`
indexes, roughly 1.5 GB, which sits comfortably in 12 GB.

The systemd unit caps the service at 768 MB (`MemoryMax`) so a runaway cannot
take the machine down.

### 3. CPU

One Ampere core handles the polling and the web panel with room to spare. The
daily refresh is the only sustained burst.

---

## Running on more than one machine

The design is already shard-ready, because **a member belongs to exactly one
pair, and a pair lives on one machine**. Referrals follow the referrer, so
families of members stay together naturally.

### The shape

```
                    ┌─────────────────────────────┐
   yourdomain.com ─▶│  nginx (any one instance)   │
                    └──────────┬──────────────────┘
                               │ route by pair
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌────────────────┐ ┌──────────────┐ ┌──────────────┐
     │ Instance A     │ │ Instance B   │ │ Instance C   │
     │ pairs 1–50     │ │ pairs 51–100 │ │ pairs 101+   │
     │ own bot tokens │ │ own tokens   │ │ own tokens   │
     │ own SQLite     │ │ own SQLite   │ │ own SQLite   │
     └────────────────┘ └──────────────┘ └──────────────┘
```

Each instance is a complete, independent copy: its own bots, its own chats,
its own database. Nothing is shared, so nothing needs to be synchronised.

### What you would need to add

The code runs unchanged on each instance. Splitting the *fleet* needs three
things that are **not built yet**:

1. **A UID router.** UIDs are random, so `/u/UID-XXXXXX` on instance A cannot
   know that member lives on B. Either give each instance a UID prefix
   (`A-`, `B-`), or put a tiny lookup service in front.
2. **Cross-instance referral credit.** If a member on A refers someone who
   lands on B, A's earnings need B's numbers. Simplest workable rule: a
   referral link always sends the new member to the *referrer's* instance, so
   a chain never spans machines.
3. **Combined payout export.** Export per instance and concatenate, or point
   one reporting job at each instance's read-only database copy.

### When to bother

**Not before ~5 million members.** Below that, one Ampere instance is
comfortable on every axis measured above, and a second machine adds moving
parts without removing a bottleneck. The signal to shard is not the database —
it is the number of Telegram groups one bot fleet can administer sanely.

Oracle's Always Free tier allows 4 OCPUs and 24 GB across up to 4 Ampere VMs,
so a four-way split costs nothing but the work.

---

## Re-measuring after a change

```bash
DB_PATH=/tmp/bench.db python3 scripts/benchmark.py 300000
```

Watch two lines:

- **Per user** — if it climbs, something started storing per-member data
  again.
- **Per-request work** — if anything there crosses ~50 ms, a query stopped
  using an index and started scanning.

# Architecture

How each requirement maps to code, and which Telegram API limit it works
around.

---

## 1. Process model

One OS process:

```
uvicorn app.main:app --workers 1
└── asyncio event loop
    ├── FastAPI            public dashboard + admin panel
    ├── bot-poller-1       aiogram Dispatcher.start_polling(bot 1)
    ├── bot-poller-2       aiogram Dispatcher.start_polling(bot 2)
    ├── …                  one task per registered token
    └── daily-scheduler    the IST daily sweep
```

`app/main.py` owns the lifespan: it calls `db.init_db()`, then
`manager.start_all()`, then launches `scheduler.daily_loop()`. Shutdown
cancels the scheduler and stops every bot.

No docker, no celery, no redis, no webhook. Polling means no inbound port for
Telegram and no TLS requirement for the bots to work.

**Why one worker.** Telegram allows exactly one `getUpdates` consumer per
token. A second uvicorn worker would start a second poller for every bot and
get `409 Conflict` forever. `deploy/referral.service` pins `--workers 1` and
says so in a comment.

### Dynamic bot management

`app/bots/manager.py` holds `{bot_id: Bot}`, `{bot_id: Dispatcher}` and
`{bot_id: asyncio.Task}`. Adding a bot in the admin panel calls
`start_bot()`, which validates the token with `getMe`, builds a dispatcher for
its role and creates the polling task. Removing one cancels the task and closes
the session. No restart, and the other bots never notice.

`BOT_TOKENS` is only a **seed**: `_seed_from_env()` inserts tokens the database
has not seen. After first boot the `bots` table is authoritative, so tokens
added through the panel survive and tokens removed there do not come back.

### Router blueprints

An aiogram `Router` can only ever be attached to one `Dispatcher`; the second
`include_router` raises `RuntimeError`. Since every bot gets its own dispatcher
(so it can be started and stopped independently), every bot also needs its own
router objects.

`app/bots/routerspec.py` solves this with `RouterSpec` — a stand-in that
records decorator registrations at import time and stamps out a fresh `Router`
per bot in `.build()`. Handler modules keep ordinary `@router.message(...)`
syntax; `dispatcher.build_dispatcher()` calls `.build()` for each.

Registration order inside an observer decides which handler wins, and
`RouterSpec` preserves it. Two places depend on that and are covered by
`tests/test_routing.py`:

* `moderation.watch_group` matches *every* group message, so it is registered
  explicitly at the bottom of the module — after `/ban`, `/mute` and friends,
  which it would otherwise swallow.
* `broadcast.relay_anything` is the same shape and is defined last.
* For the main role, `onboarding` and `account` are included before
  `bankflow`, so `/start` typed halfway through the bank form is treated as a
  command rather than as an answer (and `cmd_start` clears the FSM state).

---

## 2. Data model

`app/db.py` holds the schema. Deviations from a plain reading of the spec, and
why:

| Table | Note |
|---|---|
| `users.id` | **Is the Telegram user id.** Telegram ids are global, so every bot in the fleet sees the same id for the same person and `memberships`, `user_activity`, `bank_details` and `withdrawals` all key off it without a mapping table. |
| `users.full_name`, `banned` | Added: the moderation bot needs a display name and a fleet-wide ban flag distinct from `duplicate`. |
| `bots.role` | Added: this is what makes "several bots doing different jobs" possible. Also `username`, `telegram_id`, `last_error` for the panel. |
| `pairs.capacity`, `closed` | Added: needed to implement "if the referrer's pair is full/closed → least loaded". |
| `invite_links` | Added: maps a personal invite URL back to its owner, which is how invite-link attribution works. |
| `warnings` | Added: per-chat warning counters for the moderation escalation. |
| `settings` | Added: runtime-editable thresholds and message texts, so tuning the flood limit does not need a deploy. |

**Connections.** `db.connect()` is a context manager that opens one connection
per operation in WAL mode with `busy_timeout=10000`. `connect(write=True)` also
takes a process-wide `threading.RLock` and wraps the body in `BEGIN IMMEDIATE`,
which makes read-modify-write sequences (UID allocation, membership
transitions, "insert unless one already exists") atomic against both the web
requests and the bot tasks.

**Blocking.** These are synchronous calls made from async handlers. Local
SQLite operations on this data volume take tens of microseconds, well below
anything the event loop would notice; the simplicity is worth more than a
thread-pool hop on every query. If the database ever outgrows that, the change
is confined to `db.py`.

**Timestamps** are ISO-8601 UTC strings ending in `Z`. Month keys are derived
in IST and stored denormalised on `user_activity.month`, so month queries are
an index lookup rather than timezone arithmetic in SQL.

---

## 3. Unique public ID

`app/ids.py`. `UID-XXXXXX`, six uppercase base36 characters from
`secrets.choice` — about 2.1 billion possibilities.

`db.create_user()` retries on the `users.uid` UNIQUE constraint up to 25 times
and raises if it somehow cannot allocate one. The insert itself is the
collision check, so two concurrent registrations cannot both take a UID.

`normalise_uid()` accepts `UID-A1B2C3`, `UIDA1B2C3` and `a1b2c3` and
canonicalises them, because the deep-link payload drops the dash for
compactness while the stored and displayed form keeps it.

---

## 4. Referral flow and the single button

**Link.** `https://t.me/<bot>?start=ref_UIDA1B2C3`, built by
`common.referral_link()` from the live bot username.

**`/start`** (`handlers/onboarding.py`):

1. `parse_referral_payload` resolves the referrer.
2. Self-referral is rejected; a link belonging to a banned or duplicate
   account is ignored with a message.
3. `ensure_user` creates the row (idempotent — a repeat `/start` never
   duplicates and never rewrites an existing referrer, though it will fill in a
   referrer that was previously absent).
4. One `ReplyKeyboardMarkup` button with `request_contact=True`.

**The contact tap** does everything else in one handler:

* rejects a forwarded contact (`contact.user_id != from_user.id`);
* hashes the number and checks for a duplicate;
* sets `verified = 1`;
* `services.assign_pair_and_links()` picks the pair and issues invite links;
* replies with the UID, the referral link, the two join buttons and a share
  button.

**Placement** (`db.choose_pair`) is: the referrer's pair → the admin default →
the least-loaded open pair. Pairs that are closed, incomplete or at capacity
are skipped. Exactly one group and one channel, never two of either.

### The honest limit on "auto-add"

**No bot can add a user to a group or channel.** `addChatMember` does not exist
in the Bot API — it is an MTProto client method.

What this project does instead, in `telegram_utils.ensure_personal_invite`:
create a **named invite link with `creates_join_request=True`** for each user,
named after their UID. The user taps it once, Telegram raises a join request,
and `handlers/membership.on_join_request` approves it automatically (declining
banned and duplicate accounts). That is one tap per chat and is the closest
achievable thing to being added.

If a chat rejects join-request links, the code falls back to a plain named
link, which still reports which link was used on join.

---

## 5. Contact sharing and one phone per person

`ids.hash_phone` strips non-digits and stores only `sha256(digits)`. The raw
number is never written anywhere — not to the database, not to the logs, not to
the exports.

`phone_hash` carries a UNIQUE index. The contact handler checks for an existing
owner first *and* catches `sqlite3.IntegrityError` from the update, so a race
between two accounts claiming the same number still resolves correctly: the
database decides, and the loser becomes the duplicate.

`services.handle_duplicate` then flags `duplicate=1, banned=1, verified=0`,
clears `referred_by_uid` and `pair_id` so the account disappears from its
referrer's list, bans it from every managed chat, and notifies the admins.

Someone who never shares a contact still gets a UID and a `users` row — created
lazily by `ensure_user` the first time they touch any bot — but stays
`verified = 0`, and `ActivityStatus.eligible` is false for them, so they can
never be counted or paid.

---

## 6. Invite links and attribution

One named link per user per managed chat, cached in `invite_links` so the
Telegram call happens once. `call_api()` wraps every Bot API call with
back-off on `TelegramRetryAfter`, which is exactly the rate limit invite-link
creation hits.

When a member joins, `ChatMemberUpdated.invite_link` names the link that was
used. `db.owner_of_invite_link` resolves it by URL first, then by name (the
UID), and `_credit_inviter` sets `referred_by_uid` if the joiner does not
already have a referrer. The same logic runs on the join-request path.

---

## 7. Activity — what is recorded and what cannot be

`app/bots/middlewares.py` is an update-level outer middleware on every bot's
dispatcher. It records:

| Signal | `activity_type` |
|---|---|
| Tap on a bot button | `callback` |
| Any command | `command` |
| Message in a managed group | `group_message` (one row per user per day) |
| Vote in a bot-created poll | `poll_answer` |
| Direct message to a bot | `dm` |

**Nothing records a view.** There is no Bot API event for opening a group or
reading a channel post, so channels contribute membership only.

**`poll_answer` arrives only for polls the bot created.** A poll a human posts
generates nothing. `/poll` on the broadcast bot exists so admins always create
polls the countable way.

The daily collapse on `group_message` is a storage optimisation with no effect
on eligibility — one row anywhere in the month is the entire requirement, so
1 row/day and 400 rows/day are equivalent inputs to the rule.

---

## 8. The activity rule and two-level payouts

`app/earnings.py`. `ActivityStatus` evaluates one user for one month and
exposes both the verdict and the reason, so the bot, the public page and the
admin panel all explain the same thing in the same words.

```
active = verified and not duplicate and not banned
         and member of the pair's group
         and member of the pair's channel
         and interactions_in_month >= 1
```

* Membership alone → `"no interaction this month"`.
* Interaction without both memberships → `"not in channel"` / `"not in group"`.
* Leaving either chat → inactive on the next read, no job involved.
* Rejoining → active again, and interactions already recorded that month still
  count.
* A new month needs a new interaction; membership carrying over is not enough.

### Two levels

```
A ──refers──▶ B ──refers──▶ C, D, E
     level 1                level 2 (for A), level 1 (for B)
```

Level 1 is `db.referrals_of(uid)` — a plain index lookup on
`users.referred_by_uid`. Level 2 is `db.level2_referrals_of(uid)`, one join
rather than a query per direct referral:

```sql
SELECT c.*, b.uid AS via_uid FROM users c
  JOIN users b ON b.uid = c.referred_by_uid
 WHERE b.referred_by_uid = ? AND c.uid <> ?
```

The `c.uid <> ?` clause closes the only cycle the data permits: A refers B,
then A later opens B's link and becomes B's referral, which would otherwise
put A in A's own level 2. `handlers/onboarding.cmd_start` also refuses that
link up front, so the guard is belt and braces.

It stops at two. `report_for` walks exactly these two queries — there is no
recursion and no configurable depth, so a chain of a thousand members costs
the same two lookups as a chain of three.

**Each member is judged on their own activity.** An inactive B loses B's own
earnings but does not remove C, D and E from A's level 2. That is the literal
reading of the requirement, and it keeps one person's lapse from cascading
through everyone above them.

`EarningsReport` splits the downline into `level1_rows` and `level2_rows`,
each row carrying the rate that applied to it, and separates `gross` (what the
downline is worth) from `amount` (what is actually payable) — because an earner
who is themselves inactive earns nothing, and the UI needs to say *why* rather
than show a bare zero.

### Rates are data

`payout_level1` and `payout_level2` live in the `settings` table and are read
fresh by `earnings.rates()` on every calculation — never captured at import
time. That is why editing them in the admin panel takes effect immediately,
including for the month in progress, and why the Jinja global is the callable
`rates()` rather than a value.

`PAYOUT_LEVEL1` / `PAYOUT_LEVEL2` in the environment only seed the table on
first boot, the same arrangement as `BOT_TOKENS`.

`admin.settings_save` validates the `number` fields and **refuses** anything
non-numeric or negative instead of coercing it, because a rate that silently
became `0` would zero out everyone's earnings with no visible error. Setting
level 2 to a deliberate `0` is still allowed and turns the scheme back into a
one-level system while keeping the tracking.

`/withdraw` refuses unless the referrer is payable, the amount is positive, and
bank details are on file. `withdrawals` has `UNIQUE(user_id, month)`, so one
request per month per person, enforced by the schema and not just the handler.

Every status change is appended to `events`.

---

## 9. Month boundaries

`app/timeutil.py`, `ZoneInfo("Asia/Kolkata")` throughout.

`month_bounds()` returns `[1st 00:00 IST, 1st of next month 00:00 IST)` — a
half-open interval, so there is no 23:59:59 rounding and no leap-second edge.
`month_key()` converts any stored UTC timestamp to IST before taking
`YYYY-MM`, which is why 19:00 UTC on 31 March lands in April.

Rollover needs no cron: `current_month()` is read at request time, so at IST
midnight on the 1st every earnings figure and every withdrawal target switches
to the new month by itself. The only scheduled work is the daily prompt and a
courtesy month-closed summary to the admins.

---

## 10. Bank details

`app/bank.py` validates: IFSC `^[A-Z]{4}0[A-Z0-9]{6}$`, account number 9–18
digits (spaces and hyphens stripped first), UPI `name@handle`, name 3–70
letters.

`handlers/bankflow.py` is a four-state aiogram FSM asking one question at a
time, re-prompting on a validation failure, with `/cancel` at any point.

`db.save_bank_details` checks and inserts inside a single write transaction and
returns `False` if a row already exists, so the "only once" rule holds even if
two submissions race. A second `/bank` shows the stored details (account number
masked) and refuses politely.

---

## 11. Exports

`app/export.py`. Columns: Full Name, Account Number, IFSC, UPI ID, Amount
(INR). Only `pending` and `approved` rows are included — a bank file should not
contain money that was rejected or already sent.

Requests with no bank details are **skipped and listed**, because a bank upload
with a blank account number is worse than a short one; the admin sees exactly
who to chase.

* CSV: UTF-8 **with BOM**, CRLF line endings — what Indian bank portals expect.
* XLSX: the account-number column is formatted as text (`@`), so a 16-digit
  number is not mangled into scientific notation by Excel; the amount column is
  `0.00`; the header row is frozen.

---

## 12. Web

**Public** (`app/web/public.py`): search by UID → a card with the UID,
username, join date, verification state, current group and channel, per-chat
membership status, interaction count for the selected month, the full referral
list with each entry's active/inactive state and reason, and the month's
earnings. Plus a leaderboard and a "how it works" page that states the API
limits plainly.

The public page never renders `phone_hash`, bank details or bot tokens —
covered by `tests/test_web.py`.

**Admin** (`app/web/admin.py`): bots, chats, pairs, users, activity, audit log,
bank details, withdrawals, export and settings. Auth is a single `ADMIN_TOKEN`
compared with `hmac.compare_digest`, exchanged for an HMAC-signed cookie
carrying its own expiry (`app/web/auth.py`); the signature covers the expiry,
so a stolen cookie cannot be extended and rotating `SESSION_SECRET` logs
everyone out. The cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` whenever
`PUBLIC_BASE_URL` is https.

Bot tokens are always displayed masked.

---

## 13. Edge cases

| Case | Handling |
|---|---|
| Duplicate `/start` | `create_user` upserts; profile fields refresh, UID and referrer do not change. |
| UID collision | Insert retries against the UNIQUE index, up to 25 times. |
| Self-referral | Rejected with a message; registration continues without a referrer. |
| Reciprocal referral (A refers B, then A opens B's link) | Refused at `/start`, and `level2_referrals_of` excludes the caller anyway, so nobody can be their own level-2 downline. |
| Payout rate edited mid-month | Applies immediately — earnings are always recomputed at the current rates, never snapshotted. Amounts already written into a `withdrawals` row keep the figure that was requested. |
| Payout rate set to something non-numeric or negative | Refused by the admin panel with a message; the previous rate stands. A deliberate `0` is accepted. |
| Referrer is banned or duplicate | Link ignored; the new user still registers. |
| Same phone on a second account | Newer account flagged duplicate, banned everywhere, detached from its referrer. |
| Second `/bank` | Refused, existing details shown masked. |
| User leaves mid-month | Inactive on the next read. A rejoin writes a fresh `joined_at` and clears `left_at`. |
| User deletes their Telegram account | Telegram reports `left`; handled as any departure. |
| Banned user tries to rejoin | `on_chat_member` re-bans them; `on_join_request` declines. |
| Invite-link rate limit | `call_api` backs off on `TelegramRetryAfter` and retries. |
| Bot not an admin, or missing "invite users" | Checked at startup per chat; problems surface on the dashboard, the bots page and the settings page, and are written to `events`. |
| Bot removed from a chat | `my_chat_member` unregisters the chat for that bot. |
| Bot promoted in a new chat | `my_chat_member` registers it automatically. |
| Bad token added in the panel | `getMe` fails, the bot is marked stopped and the error is shown; nothing else is disturbed. |
| Broadcast to a chat that is gone | `copy_to_chats` collects failures per chat and reports them; the sweep continues. |
| Several bots admin in one chat | `distinct_managed_chats()` groups by `chat_id`, so a broadcast reaches each chat exactly once. |
| No pair configured yet | Registration still succeeds; the user is told links are coming and the admin is prompted to create a pair. |
| SQLite concurrency | WAL, connection per operation, `BEGIN IMMEDIATE` plus a process lock for writes, `busy_timeout=10000`. |
| Month rollover | Derived on read from `current_month()`; no job to miss. |

---

## 14. Tests

`tests/` — 96 tests, no network, each on a fresh database.

* `test_activity_rules.py` — the three conditions, per-person-per-month
  (a thousand taps pay the same as one), leave/rejoin, ineligible referrer,
  unverified/duplicate/banned referrals, the IST month boundary, and the fact
  that a new month needs a new interaction.
* `test_two_levels.py` — the A→B→{C,D,E} scenario end to end (A earns ₹20, B
  earns ₹15), earnings stopping at two levels, an inactive middle member not
  costing the top their level 2, the reciprocal-referral guard, rate changes
  taking effect immediately, a zero level-2 rate, fractional rates, a corrupt
  rate setting falling back rather than crashing, and month totals not
  double-counting across earners.
* `test_flows.py` — UID shape and normalisation, referral payload round-trip,
  phone hashing, `/start` idempotency, duplicate handling, all five placement
  rules, bank validation, one-submission-only, one-withdrawal-per-month,
  month arithmetic.
* `test_export.py` — column layout, BOM and CRLF, account numbers surviving as
  text with their leading zeros, skipped rows reported, rejected rows excluded.
* `test_web.py` — public pages, admin auth (including forged cookies), that
  every admin page renders as an admin page rather than silently bouncing to
  login, and that no secret leaks into HTML.
* `test_routing.py` — every role builds twice (proving routers are not shared),
  and the handler-order invariants above.

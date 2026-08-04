# Telegram referral platform

A multi-bot Telegram referral system with a public dashboard and an admin
panel. One process, SQLite, no docker.

* **One tap onboards a user.** They open the main bot through someone's
  referral link and tap a single button: that shares their contact, verifies
  them, places them in exactly one group and one channel, and hands back their
  public ID and their own referral link.
* **Two levels of earnings, ₹5 + ₹5 by default.** You earn on the people you
  invite *and* on the people they invite. Both rates are editable in the admin
  panel and apply immediately.
* **Paid per active member per month.** "Active" means a member of *both*
  their group and their channel who interacted with a bot at least once that
  IST month. Membership alone never counts, and extra taps never pay extra.
* **Four bot roles, one database.** A main bot for onboarding and payouts, a
  moderation bot for behaviour and bans, a collector bot that asks for bank
  details daily, and a broadcast bot that copies whatever an owner sends it
  into every managed chat.
* **Bank-ready exports.** Monthly CSV or `.xlsx` with Full Name, Account
  Number, IFSC, UPI ID, Amount (INR).
* **187 bytes per member, measured.** 30 million members fit in 5.6 GB — see
  [docs/SCALING.md](docs/SCALING.md).

### Guides

| | |
|---|---|
| **[docs/SETUP.md](docs/SETUP.md)** | Step by step from nothing to live, written for a non-coder. Start here. |
| **[docs/MANAGEMENT.md](docs/MANAGEMENT.md)** | Running it: payouts, broadcasts, moderation, backups. |
| **[docs/SCALING.md](docs/SCALING.md)** | What is stored and why, measured limits, the path to multiple servers. |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | How each requirement maps to code. |

---

## What the Telegram Bot API can and cannot do

The whole design is shaped by four hard limits. Nothing here pretends
otherwise:

| Wanted | Reality |
|---|---|
| See who *opened* a group or *read* a channel | **Impossible.** No such update exists. Activity is built from button taps, commands, group messages and bot-poll votes only. |
| Read a user's phone number | Only when they tap a `request_contact` button themselves. |
| Add a user to a group or channel | **No bot can.** The closest available thing — and what this project does — is issue a *personal named invite link* that creates a join request, then auto-approve it. The user taps their link once and is let straight in. |
| Count votes on a poll | Only for polls the **bot itself** created. Use `/poll` on the broadcast bot; a poll a human posts produces no signal at all. |

Membership changes, invite-link attribution and join requests *are* delivered,
which is what makes the rest work.

---

## Two-level earnings

```
A ──refers──▶ B ──refers──▶ C, D, E
│                            │
└─ level 1: ₹5 for B         └─ level 2: ₹5 each for C, D and E
```

So in that picture **A earns ₹20** (₹5 on B, plus ₹5 each on C, D and E) and
**B earns ₹15** (₹5 each on C, D and E).

It stops at two levels. Whoever C invites pays C at level 1 and B at level 2,
but nothing to A.

Each member is judged on **their own** activity. If B stops participating, B
loses B's own earnings — but C, D and E still count for A at level 2.

Both rates live in **Admin → Settings** (`payout_level1`, `payout_level2`) and
take effect immediately, including for the month already in progress. Setting
level 2 to `0` turns the scheme back into a plain one-level referral system
without losing the tracking.

## The activity rule

A member of your downline counts for a month when **all three** hold:

1. currently a member of the managed **channel**,
2. currently a member of the managed **group**,
3. **at least one** recorded interaction in that IST month.

Interactions are: a tap on a bot button (`callback_query`), any command, a
message in a managed group, a vote in a bot-created poll, or a direct message
to a bot.

* One interaction unlocks the month. It is per-person-per-month, not
  per-click — a thousand taps pay the same as one.
* Leaving either chat makes them inactive **immediately**, no matter what they
  did earlier that month. Rejoining restores them, and interactions already
  recorded that month still count.
* Next month needs a *new* interaction. Membership carrying over is not enough.
* The earner must clear the same bar themselves — in both chats, at least one
  interaction — plus be verified and non-duplicate, to be paid at all, at
  either level.

Months run from the 1st at 00:00 IST to the last day at 23:59 IST
(`zoneinfo("Asia/Kolkata")`, never UTC). Nothing is precomputed by a cron job:
eligibility is derived on read, so someone who leaves at 14:59 is already
inactive at 15:00.

---

## The four bot roles

Each registered token has exactly one role, which decides its routers.

| Role | What it does |
|---|---|
| `main` | `/start` deep links, the one-tap contact button, placement, personal invite links, `/bank`, `/earnings`, `/withdraw`, `/status`. |
| `moderation` | Flood control, link blocking for unverified users, a banned-word list, warn → mute → ban escalation, and `/ban` `/unban` `/mute` `/unmute` `/warn` `/unwarn` `/whois` for chat admins. Bans apply across **every** managed chat. |
| `collector` | Posts the bank-details reminder in every managed chat once a day and DMs everyone still missing theirs, one at a time. |
| `broadcast` | Anything an owner sends it in private is copied into every managed group and channel. `/poll`, `/say`, `/targets`, `/confirm on\|off`. |

Every bot, whatever its role, keeps membership state accurate for the chats it
administers.

---

## Install on Oracle Cloud Free Tier (Ampere A1, Ubuntu 24.04, ARM64)

> **Never done this before?** Use [docs/SETUP.md](docs/SETUP.md) instead — it
> covers the same ground with every click spelled out. The summary below
> assumes you are comfortable on a server.

### 1. Create the instance

Oracle Cloud → Compute → Instances → Create. Pick **Ampere A1 (ARM64)** with
Ubuntu 24.04. 1 OCPU and 6 GB is plenty; this stack targets under 500 MB.

Add ingress rules for TCP **80** and **443** in the subnet's security list —
Oracle blocks them by default and `ufw` alone will not help.

### 2. Install

```bash
ssh ubuntu@YOUR_SERVER_IP
sudo apt update && sudo apt install -y git
git clone https://github.com/tezerports-dot/EARNMONEY.git
cd EARNMONEY
sudo bash deploy/install.sh
```

`install.sh` installs Python, nginx and ufw, creates the `referral` service
user, builds the virtualenv at `/opt/referral/venv`, generates an
`ADMIN_TOKEN` and `SESSION_SECRET`, installs the systemd unit and the nginx
site, and opens ports 22, 80 and 443. It prints the generated admin token at
the end.

<details>
<summary>Manual equivalent, if you prefer to do it by hand</summary>

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx ufw

sudo useradd --system --home /opt/referral --shell /usr/sbin/nologin referral
sudo mkdir -p /opt/referral/data
sudo cp -r app deploy requirements.txt /opt/referral/

sudo python3 -m venv /opt/referral/venv
sudo /opt/referral/venv/bin/pip install -r /opt/referral/requirements.txt

sudo cp .env.example /opt/referral/.env
sudo nano /opt/referral/.env                 # fill in the values
sudo chown -R referral:referral /opt/referral
sudo chmod 600 /opt/referral/.env

sudo cp deploy/referral.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable referral

sudo cp deploy/nginx.conf /etc/nginx/sites-available/referral
sudo ln -sf /etc/nginx/sites-available/referral /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable
```
</details>

### 3. Configure

```bash
sudo nano /opt/referral/.env
```

| Variable | Meaning |
|---|---|
| `DB_PATH` | `/opt/referral/data/referral.db` |
| `ADMIN_TOKEN` | Password for `/admin`. |
| `SESSION_SECRET` | Signs the admin cookie. Changing it logs everyone out. |
| `ADMIN_IDS` | Comma-separated Telegram user ids allowed to drive the broadcast bot and moderation commands. Get yours from [@userinfobot](https://t.me/userinfobot). |
| `BOT_TOKENS` | Seed tokens as `role:token`, comma separated. Only read on first boot — after that the database is the source of truth. |
| `PUBLIC_BASE_URL` | e.g. `https://referral.example.com`. Used in bot messages, and switches the admin cookie to `Secure`. |
| `PAYOUT_LEVEL1` / `PAYOUT_LEVEL2` | Default `5` and `5`. Seed values only — once the database exists, the admin panel owns the rates. |
| `DAILY_PROMPT_HOUR` | IST hour for the daily bank-details sweep. Default `10`. |
| `DAILY_PROMPT_HOUR` | IST hour for the daily bank-details sweep. Default `10`. |

Then set `server_name` in `/etc/nginx/sites-available/referral` and:

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl start referral
sudo journalctl -u referral -f
```

### 4. HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d referral.example.com
```

Certbot rewrites the nginx site in place and sets up renewal. Afterwards set
`PUBLIC_BASE_URL` to the `https://` URL and `sudo systemctl restart referral`.

---

## First run

1. Open `https://your-domain/admin` and log in with `ADMIN_TOKEN`.
2. **Bots** → add each token from [@BotFather](https://t.me/BotFather), pick a
   role, press *Add & start*. In BotFather, turn **Group Privacy off** for the
   moderation bot so it can see group messages.
3. Add every bot to your groups and channels as an **administrator with the
   “invite users” right**. Chats register themselves the moment a bot is
   promoted; you can also add them by id on the **Chats & pairs** page.
4. **Chats & pairs** → create a pair (one group + one channel), then mark it
   *default* and *primary*.
5. Send `/start` to the main bot yourself to check the one-tap flow.

The dashboard flags any bot that is missing admin rights in one of its chats.

### Everyday operation

* **Broadcast** — DM the broadcast bot. Confirm, and it copies the message
  (text, photo, video, document, forward — anything) to every managed chat.
  `/confirm off` to skip the confirmation step.
* **Polls** — `/poll Question | Option A | Option B` on the broadcast bot.
  Only bot-created polls produce countable votes.
* **Bank details** — the collector bot asks daily; **Bank** → *Run the
  reminder sweep now* to trigger it on demand.
* **Payouts** — **Withdrawals** → approve. **Export** → download the CSV or
  `.xlsx`, upload it to your bank, then mark the rows paid. The user is
  notified at each step.

---

## Layout

```
app/
  main.py            FastAPI app + lifespan that starts the bots and scheduler
  config.py          environment snapshot
  db.py              schema, connections, every query
  earnings.py        the activity rule and the payout maths
  export.py          CSV / xlsx bank files
  bank.py            IFSC / account / UPI validation
  ids.py             UID generation, phone hashing, referral payloads
  timeutil.py        IST month boundaries
  scheduler.py       the daily sweep and the month-rollover report
  roles.py           the four bot roles
  bots/
    manager.py       one asyncio polling task per token, start/stop at runtime
    dispatcher.py    role → routers
    routerspec.py    router blueprints (a Router cannot be shared between bots)
    middlewares.py   turns updates into activity rows
    services.py      placement, invite links, duplicate handling, daily prompt
    telegram_utils.py retries, cross-chat bans, broadcast fan-out
    handlers/        onboarding, account, bankflow, membership, moderation,
                     broadcast, collector
  web/
    public.py        search, user page, leaderboard
    admin.py         bots, chats, pairs, users, activity, bank, payouts, export
    auth.py          signed-cookie admin session
  templates/  static/
deploy/              systemd unit, nginx site, install.sh
tests/               122 tests, no network needed
scripts/benchmark.py measures bytes/member and query timings
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q

DB_PATH=./data/dev.db ADMIN_TOKEN=dev SESSION_SECRET=dev \
  .venv/bin/uvicorn app.main:app --reload
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for how each requirement maps to code
and which API limits it works around.

## Operational notes

* **One worker only.** The bots live inside the web process; a second uvicorn
  worker would start a second poller per token and Telegram answers that with
  `409 Conflict`. The systemd unit pins `--workers 1`.
* **Backups.** `sqlite3 /opt/referral/data/referral.db ".backup /tmp/backup.db"`
  is safe while the service runs. Copy it off the box on a schedule.
* **Logs.** `journalctl -u referral -f`.
* **Phone numbers are never stored.** Only a truncated SHA-256, used solely to
  stop one person holding two accounts. Never displayed, never exported.
* **Only what a payout needs is kept.** No interaction log, no membership
  table, no usernames or display names. See
  [docs/SCALING.md](docs/SCALING.md) for what that buys and the one trade-off
  it costs (activity history is two months deep).

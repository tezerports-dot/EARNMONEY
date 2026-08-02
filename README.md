# Telegram Referral Platform

A Telegram-first referral platform: users join via a bot, get auto-assigned to a channel + group
shard, activate after 24h of dual membership, and earn a flat admin-set payout (₹1-5) per active
referral each month. A minimal Next.js site provides a public no-login status lookup and a
login-gated admin panel.

See `telegram-referral-platform-spec.md`-equivalent behavior implemented in:
- `apps/bot` — Telegraf bot + scheduled worker (Phase 1)
- `apps/web` — public site + `/admin` panel (Phase 2)
- `packages/database` — Prisma schema/client shared by both apps
- `packages/shared` — constants and types shared by both apps

For a plain-language, click-by-click setup guide (no coding experience assumed), see
**SETUP_GUIDE.md** (Oracle Cloud Always-Free VM, split services). The steps below are the
condensed technical version.

**Deploying on Railway instead?** See **RAILWAY_DEPLOY_GUIDE.md** — a single combined
service (bot + worker + website in one process) sized to fit the free trial.

**Moving between hosts?** See **MIGRATION_GUIDE.md** for the maintenance-mode freeze +
dump/restore/verify procedure, and **ORACLE_MIGRATION_PLAN.md** for the specific
Railway → Oracle path.

## Prerequisites

- Docker + Docker Compose installed on your server
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- At least one Telegram channel and one Telegram group you own, each with an invite link, to
  register as your first shards

## 1. Configure environment

```bash
cp .env.example .env
# edit .env: set BOT_TOKEN, BOT_USERNAME, JWT_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD
```

## 2. Start the stack

```bash
docker compose up -d --build
```

This starts Postgres, Redis, runs Prisma migrations, then starts the bot (long polling until you
set `BOT_WEBHOOK_URL`), the worker, the web app, and Nginx.

## 3. Create your first admin login

```bash
docker compose run --rm web npm run seed:admin
```

This reads `ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env` and creates the first `AdminUser` row.
Log in at `http://<your-server>/admin/login`.

## 4. Register your first channel and group shard

In the admin panel, go to **Channels** and **Groups** and add your first shard for each, with:
- a shard key (any label, e.g. `channel-01`)
- the Telegram chat ID (numeric, negative for channels/supergroups — forward a message from the
  chat to [@userinfobot](https://t.me/userinfobot) or use `getUpdates` to find it)
- the invite link

**Important:** your bot must be an **admin** of both the channel and the group, with permission
to see members, or membership checks will fail.

## 5. Go live with a free subdomain (or your own domain)

Set `BOT_WEBHOOK_URL` and `NEXT_PUBLIC_SITE_URL` in `.env` to a single public HTTPS domain (a free
subdomain from DuckDNS/FreeDNS/No-IP works fine — no purchase needed). `nginx/nginx.conf` is
already set up to route everything off that one domain by path:
- `/` → public website
- `/admin` → admin panel (same Next.js app)
- `/webhook` → Telegram bot webhook

Add HTTPS with Certbot's webroot method (works with our Dockerized Nginx, zero downtime — see
`SETUP_GUIDE.md`'s "Add HTTPS" section for the exact commands),
then:

```bash
docker compose up -d --build
```

See `SETUP_GUIDE.md` for the full click-by-click version, including the free-subdomain signup steps.

## Monthly payout flow

**Eligibility rule:** a referral only counts toward a given month's payout if the referred user
became `ACTIVE` on or before the **15th of that month, Indian Standard Time**. Someone who
activates on the 23rd, for example, is excluded from that month's run — they carry over and count
starting the following month if still active by its 15th. This is enforced identically by the
worker's scheduled run and the admin panel's manual "Run Monthly Payout" button, via
`packages/shared/src/payout.ts`.

1. Admin sets the flat rate (₹1–5) for the month in **/admin/payouts**.
2. Admin clicks **Run Monthly Payout** (or the worker runs it automatically on the 30th, IST).
3. Admin reviews the batch, then exports one of three CSVs:
   - **Bulk Bank Upload** — ready to hand to your bank's bulk-transfer tool (beneficiary name,
     account number, IFSC, UPI ID fallback, amount, narration). Only includes PENDING rows that
     actually have a payment method on file.
   - **Full detail** — every row with status/audit detail, for your own records.
   - **Missing bank details** — PENDING rows where the user hasn't added a payment method yet, so
     you know who to remind to send `/bankdetails` to the bot.
4. Admin performs the actual bank transfers outside this system using the bulk file.
5. Admin marks each row **Paid** with the transaction reference.

## Why the website only updates once a day

`/check` (public) and `/status` (bot) read `User.cachedActiveReferralCount` /
`cachedPayoutEligibleReferralCount` — cached fields — instead of counting referrals live on every
request. A worker job (`runDailySnapshot` in `apps/bot/src/worker.ts`) recomputes these for every
user once every 24 hours using two aggregate queries, not one query per user, so this stays cheap
even at very large user counts. The bot's `/status` reply and the website both show when the
numbers were last refreshed.

## Local development (without Docker)

```bash
npm install
npm run prisma:push      # applies schema to your local Postgres
npm run dev -w apps/bot        # bot, long polling
npm run dev:worker -w apps/bot # scheduled worker
npm run dev -w apps/web        # website + admin
```

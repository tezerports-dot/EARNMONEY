# Railway Deploy Guide — Single Service (Trial-Friendly)

This deploys the bot + worker + website as **one Railway service**, plus one
Postgres database — 2 services total, well inside the trial's 5-service
limit. (Redis is in `docker-compose.yml` for the future, but nothing in the
code actually uses it yet, so skip it here — one less thing to pay for.)

Total time: about 20–30 minutes.

---

## Before you start
Do **Part 1 and Part 2** of `SETUP_GUIDE.md` first (create your Telegram bot
with BotFather, create your channel + group, get their chat IDs). You need:
- Your **Bot Token**
- Your **Channel Chat ID** and **Group Chat ID**
- Your channel and group **invite links**

---

## Step 1 — Push this project to GitHub
Railway deploys from a GitHub repo.
1. Create a new **private** GitHub repo (e.g. `referral-platform`).
2. Upload/push this whole folder into it (drag-and-drop on github.com works
   if you don't use git — click "uploading an existing file").

## Step 2 — Create the Railway project
1. Go to **railway.com** → sign up (GitHub login is easiest — it also helps
   verification, giving you full network access instead of the restricted
   Limited Trial).
2. Click **New Project** → **Deploy from GitHub repo** → pick your repo.
3. Railway will try to auto-detect a build — **stop**, don't let it deploy
   yet. Click the new service card → **Settings**.

## Step 3 — Point it at the combined Dockerfile
In the service's **Settings → Build**:
- **Builder:** Dockerfile
- **Dockerfile Path:** `docker/Dockerfile.combined`

## Step 4 — Add Postgres
1. In the project canvas, click **+ New** → **Database** → **Add PostgreSQL**.
2. Click the Postgres service → **Variables** tab → copy the value of
   `DATABASE_URL` (Railway generates this for you).

## Step 5 — Set environment variables on your app service
Click your app service → **Variables** → add these (paste your own values):

```
BOT_TOKEN=<from BotFather>
BOT_USERNAME=<your bot's username, no @>
DATABASE_URL=<paste from the Postgres service — or use Railway's variable
              reference picker so it stays in sync automatically>
JWT_SECRET=<any long random string>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<a strong password>
PAYOUT_MIN_INR=1
PAYOUT_MAX_INR=5
RUN_MODE=combined
MAINTENANCE_MODE=false
```

Leave `BOT_WEBHOOK_URL` and `NEXT_PUBLIC_SITE_URL` **blank for now** — you
need Railway's generated domain first (next step).

## Step 6 — Generate a public domain
1. Your app service → **Settings → Networking** → **Generate Domain**.
2. Copy the domain it gives you, e.g. `referral-platform-production.up.railway.app`.
3. Go back to **Variables** and set:
   ```
   BOT_WEBHOOK_URL=https://referral-platform-production.up.railway.app
   NEXT_PUBLIC_SITE_URL=https://referral-platform-production.up.railway.app
   ```
4. Save — this redeploys automatically. HTTPS is already handled by Railway,
   no Certbot/DuckDNS step needed here (unlike the Oracle path).

## Step 7 — Watch the deploy
Click **Deployments** → the latest one → **View Logs**. Wait for:
```
[combined] bot webhook mounted at https://.../webhook
[combined] worker scheduler started in-process
[combined] server listening on port ####
```

## Step 8 — Create your admin login
Railway → your service → **Settings → Deploy → Custom Start Command**
(temporarily), or easier: use the **Railway CLI** from your own computer:
```
npm i -g @railway/cli
railway login
railway link          # pick this project
railway run npm run seed:admin -w apps/web
```
You should see `Created admin user "admin". You can now log in at /admin/login.`

## Step 9 — Log in and register your channel/group
Same as `SETUP_GUIDE.md` Parts 9–10:
- `https://YOUR-DOMAIN/admin/login`
- Add your Channel (shard key `channel-01`) and Group (shard key `group-01`)
  with their chat IDs and invite links.

## Step 10 — Test it
Same as `SETUP_GUIDE.md` Part 11 — message your bot, join, test `/status`
and `/bankdetails`.

---

## What's different from the Oracle/VM path
- No nginx, no Certbot, no DuckDNS — Railway gives you HTTPS + a domain.
- No separate `migrate` step — the Dockerfile runs `prisma db push`
  automatically before starting the app on every deploy.
- Everything (bot + worker + website) is **one process** here, to fit
  comfortably inside the trial's service limit and keep resource usage (and
  cost) down. See `MIGRATION_GUIDE.md` for how to split it back apart or
  move elsewhere later — no code changes needed either way.

## Budget reality check
The $5 trial credit covers this comfortably for your first day of building
and testing. Under real 1000-joins/day traffic, expect the credit to last
roughly **1–2 weeks**, not the full 30 days — plan to move to Hobby ($5/mo)
or off Railway entirely before then. Turn on **usage alerts** in Railway's
billing settings so you get a warning instead of a surprise pause.

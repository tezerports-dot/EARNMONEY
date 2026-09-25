# Server setup

The server is one Docker Compose stack (`backend/docker-compose.yml`) on one machine:

| Service | What it does |
|---|---|
| `caddy` | HTTPS on ports 80 and 443, with automatic certificates. Forwards everything to `api`. |
| `api` | The FastAPI server: the app's API, the admin panel (`/admin`), referral link pages (`/r/CODE`), the APK download redirect and Telegram webhooks. |
| `worker` | Background jobs: daily referral snapshots, unlocking rewards on the payout date, expiring stale signups, re-checking unhealthy bots. |
| `migrate` | Runs database migrations, then exits. `api` and `worker` wait for it. |
| `postgres` | PostgreSQL 16, the source of truth for all data and money. |
| `redis` | Rate limits, CAPTCHA answers and short-lived Telegram state. Nothing in it needs a backup. |

Only Caddy is reachable from the internet. PostgreSQL and Redis have no published ports.

## 1. What you need

- **A server.** Ubuntu 24.04 with 2 vCPU, 4 GB RAM and 80 GB SSD is enough to launch. Pick a region in or near India (Mumbai or Bangalore) for low latency. [PERFORMANCE.md](PERFORMANCE.md) says when to grow.
- **A domain** with its DNS on Cloudflare (the free plan is enough). One domain serves everything: the API, referral links, the APK download and the Android App Links file. This guide calls it `futurefashion.example`.
- **Telegram bots and channels** (see [ADMIN.md](ADMIN.md)), created with @BotFather.

## 2. DNS

1. In Cloudflare, add an `A` record for the domain pointing at the server's IP address. Set it to **DNS only** (grey cloud) for now, so Caddy can get its first certificate directly.
2. Once `https://futurefashion.example/healthz` works (step 4), switch the record to **Proxied** (orange cloud) and set **SSL/TLS → Overview** to **Full (strict)**.

Behind the Cloudflare proxy, every request arrives from a Cloudflare address. `backend/Caddyfile` trusts the visitor address Cloudflare sends (`CF-Connecting-IP`) only from Cloudflare's published IP ranges, and passes it to the API. Without that, all users would share the per-IP limits on login and signup. Cloudflare rarely changes its ranges, but compare the list in the Caddyfile with <https://www.cloudflare.com/ips/> when you deploy.

## 3. Install and configure

```bash
# Docker, from Docker's own repository
curl -fsSL https://get.docker.com | sh

# Firewall: SSH and web only
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable

# The code
git clone https://github.com/tezerports-dot/EARNMONEY.git /opt/futurefashion
cd /opt/futurefashion/backend
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

1. Set `DOMAIN` and `FF_PUBLIC_BASE_URL` to your domain (`https://` for the second).
2. Choose a long random database password. Put it in **both** `POSTGRES_PASSWORD` and `FF_DATABASE_URL`.
3. Generate two **different** keys, one for `FF_DATA_ENCRYPTION_KEY` and one for `FF_HMAC_KEY`:

   ```bash
   python3 -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```

4. After you create the app signing key ([RELEASE.md](RELEASE.md)), put its SHA-256 fingerprint in `FF_ANDROID_CERT_SHA256`, for example `["AB:CD:…"]`.

**Back up `.env` somewhere safe outside the server** (a password manager). Without `FF_DATA_ENCRYPTION_KEY`, stored bank account numbers, bot tokens and admin 2FA secrets can't be decrypted. Without `FF_HMAC_KEY`, open verification links stop working and duplicate bank account detection resets.

## 4. Start

```bash
docker compose up -d --build
docker compose ps                       # migrate should show "exited (0)"
curl https://futurefashion.example/healthz   # {"ok":true}
curl https://futurefashion.example/readyz    # {"ok":true}: database reachable
```

Then switch Cloudflare to Proxied (step 2).

## 5. First admin

```bash
docker compose run --rm api python -m app.cli create-admin owner
```

It asks for a password (12+ characters) and prints an `otpauth://` link. Add that to an authenticator app now (Google Authenticator, Authy, 1Password…); it isn't shown again. Sign in at `https://futurefashion.example/admin`, then follow the first-time checklist in [ADMIN.md](ADMIN.md). Run the same command with another name to add more admins.

## 6. Backups

PostgreSQL holds everything that matters. Take a nightly dump and copy it off the server, for example to Cloudflare R2 with `rclone`:

```bash
# /etc/cron.d/futurefashion-backup
0 2 * * * root cd /opt/futurefashion/backend && docker compose exec -T postgres pg_dump -U futurefashion -Fc futurefashion > /var/backups/ff-$(date +\%F).dump && find /var/backups -name 'ff-*.dump' -mtime +14 -delete
```

Test a restore before you need one:

```bash
docker compose exec -T postgres pg_restore -U futurefashion -d futurefashion --clean --if-exists < /var/backups/ff-2026-12-30.dump
```

Dumps contain encrypted bank numbers and hashed passwords. They can only be decrypted with the keys in `.env`, so keep the two in different places.

## 7. Updates

```bash
cd /opt/futurefashion && git pull
cd backend && docker compose up -d --build
```

`migrate` applies new migrations before `api` and `worker` restart. For risky changes, switch on maintenance mode in the admin panel first. The app shows your message, with a Retry button, until you switch it off.

## 8. Keeping an eye on it

- **Logs** are JSON lines on standard output: `docker compose logs -f api worker`. They never contain passwords, tokens, OTPs or full bank numbers.
- **Health:** `/healthz` (process up) and `/readyz` (database reachable). Point an uptime monitor at `/readyz`.
- **Admin dashboard:** sign-ups, pool balance, withdrawals, open fraud flags, and the job queue with the age of its oldest ready job.
- **Ledger check,** daily from cron. It exits with code 2 if balances and entries ever disagree:

  ```bash
  docker compose exec -T api python -m app.cli check-ledger
  ```

## Configuration reference

Campaign dates, rewards, bots, channels, maintenance mode, ads and legal details are changed in the admin panel without a restart. These deployment settings live in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `DOMAIN` | — | Domain Caddy serves and gets a certificate for (compose only). |
| `POSTGRES_PASSWORD` | — | Database password (compose only). Must match `FF_DATABASE_URL`. |
| `FF_ENV` | `dev` | `dev`, `test`, `staging` or `production`. Staging and production refuse the built-in development keys and plain `http`. |
| `FF_PUBLIC_BASE_URL` | `http://localhost:8000` | Public address of this server. Used for referral links, Telegram webhooks and the APK download. |
| `FF_DATABASE_URL` | local `ff_dev` | PostgreSQL connection (`postgresql+asyncpg://…`). |
| `FF_DATABASE_POOL_SIZE` / `FF_DATABASE_MAX_OVERFLOW` | `10` / `20` | Database connections per process. |
| `FF_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection. |
| `FF_DATA_ENCRYPTION_KEY` | dev key | 32-byte base64 key. AES-256-GCM for bank numbers, bot tokens and admin 2FA secrets. |
| `FF_HMAC_KEY` | dev key | 32-byte base64 key, different from the one above. Fingerprints and verification link tokens. |
| `FF_ACCESS_TOKEN_MINUTES` | `15` | App access token lifetime. |
| `FF_REFRESH_TOKEN_DAYS` | `30` | How long a login lasts without use. |
| `FF_PENDING_ACCOUNT_HOURS` | `24` | Unverified signups are removed after this, freeing the number. |
| `FF_ADMIN_SESSION_HOURS` | `8` | Admin panel session lifetime. |
| `FF_ARGON2_TIME_COST` / `FF_ARGON2_MEMORY_KIB` / `FF_ARGON2_PARALLELISM` | `3` / `65536` / `2` | Password hashing cost. |
| `FF_TRUST_PROXY_HEADERS` | `false` | Read the client IP from `X-Forwarded-For`. Compose sets it to `true` because Caddy is in front. |
| `FF_TELEGRAM_API_BASE` | `https://api.telegram.org` | Telegram Bot API address. |
| `FF_ANDROID_PACKAGE_NAME` | `com.futurefashion.app` | App id, for Android App Links. |
| `FF_ANDROID_CERT_SHA256` | `[]` | SHA-256 fingerprints of the release signing certificate (JSON list). |
| `FF_LOG_LEVEL` | `INFO` | Log level. |

## Local development

```bash
# PostgreSQL and Redis, any way you like, for example:
docker run -d --name ff-pg -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16
docker run -d --name ff-redis -p 6379:6379 redis:7
docker exec ff-pg createdb -U postgres ff_dev
docker exec ff-pg createdb -U postgres ff_test

cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[test]" "ruff==0.16.8"
export FF_DATABASE_URL=postgresql+asyncpg://postgres:dev@127.0.0.1:5432/ff_dev
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload       # API on http://localhost:8000
.venv/bin/python -m app.cli worker            # background jobs, in another terminal
```

The Android emulator reaches your computer at `10.0.2.2`, which is what `mobile/config/dev.json` uses. Telegram can only deliver webhooks to a public HTTPS address, so to try verification locally, expose port 8000 through a tunnel and set `FF_PUBLIC_BASE_URL` to it.

Tests use their own database, which they wipe:

```bash
FF_TEST_DATABASE_URL=postgresql+asyncpg://postgres:dev@127.0.0.1:5432/ff_test .venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

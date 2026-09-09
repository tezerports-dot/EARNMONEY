# Job Referral Platform

Referral-and-training-gated job application platform for retail-outlet
hiring. Built from the spec in `/docs-source` (original 8-file pack), with
two deliberate deviations recorded in `docs/SPEC-DEVIATIONS.md` — read that
file before touching the referral or KYC-challenge logic.

## Status

**Stage 1–2 complete** (repo scaffold, database schema, auth, referral
crediting, KYC-training challenge engine, applications). The API boots,
serves, and has been exercised end-to-end against a real Postgres:
signup → login → `identity/start` → signed provider webhook → status
advances to `TELEGRAM_PENDING`, with audit rows written at each step.

**Not yet built:** real identity/KYC provider integration, Telegram bot,
admin panel, and the candidate-facing frontend. Because the Telegram module
is not wired in, a candidate currently stops at `TELEGRAM_PENDING` — that is
the next thing to build. See "What's next" below and `HANDOFF.md`.

## Architecture

```
apps/api/          NestJS backend (this is what's built so far)
  prisma/           Database schema + migrations + seed data
  src/
    auth/           Signup, login, refresh, logout, CAPTCHA interface
    users/          Profile + status-transition logic (activateUser)
    referrals/      Server-side referral crediting
    eligibility/    Single source of truth for "has this candidate met
                     both thresholds yet"
    kyc-training/   Synthetic-data KYC competency challenges
    applications/   Job application submission, gated on eligibility
    system-config/  Admin-tunable thresholds (never hardcoded)
    audit/          Append-only audit log
    common/         Guards (JWT, roles, CSRF), filters, decorators
infra/nginx/        Reverse proxy + TLS config for production
docker-compose.yml       Local development
docker-compose.prod.yml  Production (Hostinger VPS)
```

## Migrations

The initial migration is generated and committed
(`apps/api/prisma/migrations/20260909125114_init/`), and was verified by
applying it to an empty Postgres 16 database and running the seed against
the result. Nothing one-time is left to do — `prisma migrate deploy` only
applies existing SQL, so it works in restricted environments too.

`infra/scripts/init-migration.sh` remains for regenerating from scratch if
you ever reset the schema; for ordinary schema changes use
`npx prisma migrate dev --name <change>` and commit the new folder.

## Local development

Requires Docker and Docker Compose.

```bash
cp .env.example .env        # fill in at least JWT secrets; DB defaults are fine locally
docker compose up --build
```

This starts Postgres, Redis, and the API with hot reload on `:3001`, and runs
`prisma migrate deploy` automatically on boot. To seed the default thresholds
and sample KYC training scenarios:

```bash
docker compose exec api npx prisma db seed
```

### Running tests

```bash
cd apps/api
npm ci
npx prisma generate     # writes the typed Prisma Client into node_modules
npm test                # 38 unit tests
npm run lint
npm run build           # emits dist/main.js, what the production image runs
```

`prisma generate` needs to reach `binaries.prisma.sh` once per checkout to
download the query engine. It is not a build-time blocker anywhere else —
the Dockerfile runs it in both stages.

## Deploying to Hostinger

**You need a VPS (KVM) plan** — Postgres and Redis aren't available on
Hostinger's shared/Cloud hosting, only on VPS. KVM 2 (8GB RAM / 2 vCPU) is
comfortable for Postgres + Redis + API + (later) the frontend as separate
containers.

1. **Provision the VPS** with the Ubuntu 24.04 + Docker template (Hostinger
   offers this directly in hPanel — search "Docker" under OS templates), or
   install Docker yourself on a plain Ubuntu image:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
2. **Point your domain** at the VPS's IP address (A record) before
   requesting a TLS certificate.
3. **Upload the repo** (git clone, or scp the folder) to the VPS.
4. **Configure secrets**:
   ```bash
   cp .env.example .env
   nano .env   # fill in DB password, JWT secrets (openssl rand -base64 48), domain
   ```
5. **Edit `infra/nginx/app.conf`** — replace `your-domain.example` with your
   real domain (two places).
6. **First-time HTTPS certificate** (before starting Nginx with SSL config,
   or using a temporary HTTP-only config first):
   ```bash
   docker compose -f docker-compose.prod.yml run --rm certbot certonly \
     --webroot -w /var/www/certbot -d your-domain.example
   ```
7. **Start everything**:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.prod.yml exec api npx prisma migrate deploy
   docker compose -f docker-compose.prod.yml exec api npx prisma db seed
   ```
8. **Verify**: `curl https://your-domain.example/api/v1/health` should return
   `{"status":"ok",...}`.
9. **Firewall**: only ports 80 and 443 need to be open publicly (Hostinger's
   VPS firewall in hPanel, or `ufw`). Postgres and Redis are not published to
   the host in `docker-compose.prod.yml` — keep it that way.

### Before this can go live for real candidates

- Set `TURNSTILE_SECRET_KEY` — signup/login currently run with a CAPTCHA
  stub that always passes (`NoopCaptchaService`). Fine for development,
  **not fine for production**.
- Select and contract with a licensed identity/KYC verification provider —
  this repo does not implement Aadhaar/ID verification itself, and shouldn't
  (see 01-PRD.md's own non-goals). That integration is the next stage.
- Create your Telegram bot via [@BotFather](https://t.me/BotFather) and wire
  `TELEGRAM_BOT_TOKEN` — also next stage.
- Get someone to actually review `docs/SPEC-DEVIATIONS.md` and the identity
  data-handling approach against India's DPDP Act before launch. Nothing
  here substitutes for that review.

## What's next

In the order the original spec recommends:
1. Identity/KYC provider integration (pluggable `IdentityProvider` interface
   + webhook handling)
2. Telegram bot (bind account, verify group membership)
3. Admin panel (review flagged accounts, adjust thresholds, manage vacancies
   and training batches, expand the KYC scenario bank)
4. Candidate-facing frontend (Next.js)
5. Load testing and a security review pass before go-live

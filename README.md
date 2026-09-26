# Future Fashion — referral rewards app

A referral rewards campaign for the Future Fashion launch: a Flutter Android
app, and the server it depends on. Invite a friend; when they sign up with your
code and verify through Telegram, you earn **₹200**. Rewards are paid from a
promotional pool on the payout date (31 December 2026).

The same Flutter codebase is structured to be publishable to Google Play and,
later, the App Store.

## What it is, honestly

This project follows a strict product-integrity rule (see `CLAUDE.md`): no
fabricated numbers, no fake users, no guaranteed-earnings claims, nothing hidden.

- **One paid level.** ₹200 for each friend you refer **directly** who verifies.
- **Four levels shown, only level 1 pays.** The referral table counts levels 2–4
  so you can see how far your invitations spread, but they earn **₹0** — fixed in
  server code and by database `CHECK` constraints, not an admin setting.
- **Real numbers only.** The member counter is the true count of verified users,
  computed by the server. Nothing is seeded or inflated.
- **Money is real ledger state.** Integer paise, double-entry, append-only.

## Layout

```
mobile/     Flutter Android app (all screens, API client, tests)
backend/    FastAPI server: auth, Telegram verification, referrals, ledger,
            wallet, withdrawals, admin panel, background worker
e2e/        End-to-end harness: real app ↔ real server ↔ fake Telegram
security/   Security probe against a local instance
docs/       Contracts, schema, setup, release, admin, performance, pentest
```

## Documentation

| Doc | What it covers |
|---|---|
| `CLAUDE.md` | The full specification and the agreed product decisions |
| [docs/PLAN.md](docs/PLAN.md) | Architecture, APK-vs-server split, assumptions, open items |
| [docs/API.md](docs/API.md) | The v1 API contract |
| [docs/DATABASE.md](docs/DATABASE.md) | Schema and the rules the database enforces |
| [docs/APP.md](docs/APP.md) | App navigation and design tokens |
| [docs/SETUP.md](docs/SETUP.md) | Deploying and running the server |
| [docs/RELEASE.md](docs/RELEASE.md) | Signing and building the APK; how sharing works |
| [docs/ADMIN.md](docs/ADMIN.md) | Running the campaign from the admin panel |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Benchmark method, results, capacity planning |
| [docs/PENTEST.md](docs/PENTEST.md) | Security testing and findings |
| [SECURITY.md](SECURITY.md) | Security checklist and the abuse-case map |

## Run it locally

**Server** (needs PostgreSQL 16 and Redis 7):

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[test]" "ruff==0.16.8"
export FF_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/ff_dev
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload      # API on :8000
.venv/bin/python -m app.cli worker           # background jobs, another terminal
```

**App** (needs Flutter 3.47):

```bash
cd mobile
flutter pub get
flutter run --flavor dev --dart-define-from-file=config/dev.json
```

The Android emulator reaches the server at `10.0.2.2:8000` (`config/dev.json`).
For a real deployment behind Cloudflare and Caddy, see [docs/SETUP.md](docs/SETUP.md).

## Tests

```bash
# Backend (real Postgres + Redis)
cd backend && FF_TEST_DATABASE_URL=…/ff_test .venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .

# App
cd mobile && flutter analyze && flutter test

# End to end (app ↔ server ↔ fake Telegram) and the security probe
FF_E2E_DATABASE_URL=…/ff_e2e e2e/run.sh
FF_SEC_DATABASE_URL=…/ff_sec security/run.sh

# Benchmark
cd backend && FF_BENCH_DATABASE_URL=…/ff_bench .venv/bin/python -m bench.run
```

CI (`.github/workflows/ci.yml`) runs the backend suite and migrations, the app
format/analyze/test/release-APK build with the APK-signature tests, and the
end-to-end journey plus the security probe.

## Status

The app and server are built and tested end to end; the release APK builds. A
short list of things only Future Fashion can provide before launch — the
registered company details, a domain and server, the signing key, the Telegram
bots and channels, and funding for the reward pool — is in
[docs/PLAN.md](docs/PLAN.md) and [SECURITY.md](SECURITY.md).

## Tech

Flutter 3.47 (Riverpod, go_router, dio) · FastAPI · SQLAlchemy 2 + asyncpg ·
PostgreSQL 16 · Redis 7 · Alembic. Money in integer paise, double-entry ledger.

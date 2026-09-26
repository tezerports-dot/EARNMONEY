# Phase 1 — Discovery and implementation plan

Future Fashion referral app. Written 24 September 2026, before any application code.

## In plain words

- The app is an Android APK built with Flutter. Everything that involves money, referrals, verification or counts lives on a server that we also build. The APK only shows what the server says.
- A user signs up with their Indian mobile number and a password, then verifies in Telegram: they join the required channels and share their Telegram contact. The server checks that number matches the one they signed up with.
- A user earns ₹200 for each friend they refer directly who completes verification. The referral table shows four levels, and levels 2–4 show real counts with ₹0.
- Rewards stay pending until the payout date (31 December 2026). From then, users can ask for their balance to be paid to their saved bank account.
- Every number on screen is real: the member counter, the referral counts, the wallet. The ₹0 for levels 2–4 is fixed in the code and the database, so it can't be switched to a paid level from the admin panel.

## Repository state

| Item | State |
|---|---|
| Application code | None. The repository was emptied on request (pull request #3). The previous Python Telegram platform is in git history only and is not reused, because the product model is different. |
| Specification | `CLAUDE.md`, updated with the agreed decisions at the top. |
| `pubspec.yaml`, Android/iOS config, routing, API client, auth, tests, CI | None yet. All are created in this project. |

## Toolchain on the build machine

| Tool | Version | Used for |
|---|---|---|
| Flutter / Dart | 3.47.5 / 3.13.4 (stable, 18 Sep 2026) | `flutter analyze`, `flutter test`, `flutter build apk` |
| Android SDK | platform 36, build-tools 36.1.0 | APK builds |
| Java | OpenJDK 21 | Gradle |
| Python | 3.11 (production image uses 3.12) | Backend |
| PostgreSQL | 16 | Backend database and tests |
| Redis | 7 | Rate limits, CAPTCHA, cache |

There's no Android device or emulator, so on-device testing (APK sharing, deep links, ads) has to happen on real phones. See [Blockers](#potential-blockers).

## Architecture

```text
                ┌───────────────────────────┐
  Android APK   │ Flutter app               │  UI, animations, validation, API client,
  (Flutter)     │  Riverpod · go_router · dio│  secure token storage, sharing, ads
                └─────────────┬─────────────┘
                              │ HTTPS /v1 (JSON)
                ┌─────────────▼─────────────┐        ┌──────────────────┐
  Server        │ API (FastAPI)             │◀───────│ Telegram Bot API │
                │  auth · referrals · wallet│ webhooks│ verifier bots +  │
                │  withdrawals · config     │───────▶│ channel watcher  │
                │  Telegram webhooks        │        └──────────────────┘
                │  admin panel (/admin)     │
                └──────┬──────────────┬─────┘
                       │              │
                ┌──────▼─────┐  ┌─────▼─────┐   ┌────────────────────────┐
                │ PostgreSQL │  │  Redis    │   │ Worker                 │
                │ all data,  │  │ rate limits│  │ jobs table in Postgres │
                │ ledger     │  │ CAPTCHA   │   │ snapshots · unlocks ·  │
                └────────────┘  └───────────┘   │ bot health             │
                                                └────────────────────────┘
```

### What lives in the APK vs on the server

| APK | Server |
|---|---|
| Screens, design system, fonts, illustrations, animations | Accounts, password hashes, sessions |
| Form validation (format only) | Referral binding, reward crediting, the ledger |
| API client, token storage (Android Keystore via secure storage) | Wallet balances, withdrawals, bank details (encrypted) |
| Countdown rendering using server time | Campaign dates, reward amount, payout date, capacity |
| Sharing the app, referral link and code | Telegram bot tokens, channel IDs, verification results |
| Ad display using remote settings | Rate limits, CAPTCHA answers, fraud flags, audit log |
| No secrets, no admin controls | Admin panel with password + one-time code (TOTP) |

### Backend

- **Python + FastAPI**, async SQLAlchemy 2 on **PostgreSQL**, Alembic migrations, **Redis** for rate limits and CAPTCHA.
- **Money** is integer paise everywhere. Balances change only through a double-entry ledger: every transaction's entries sum to zero, and user balances have database `CHECK (balance >= 0)` constraints.
- **Referrals** use a depth-limited closure table: each new user gets up to four rows, one per ancestor level. The referrer is fixed at signup and never changes. Counting levels is an indexed query, and the dashboard reads a daily snapshot.
- **Rewards**: when a referred friend verifies, the same database transaction creates exactly one level-1 reward. A unique constraint on the source user stops double credit, and `CHECK (level = 1)` stops paid deeper levels. The money moves from the promotional pool account to the referrer's pending balance, and the pool can't go negative.
- **Telegram**: one *watcher* bot is an admin in the required channels and records join requests. A configurable pool of *verifier* bots talks to users. Tokens are encrypted at rest, and webhooks are authenticated with Telegram's secret-token header.
- **Jobs**: a small queue table in Postgres (`SELECT … FOR UPDATE SKIP LOCKED`) with retries, backoff with jitter, dedupe keys and a concurrency limit. It handles snapshot refreshes, the payout-date unlock and bot health checks.
- **Admin panel**: server-rendered pages at `/admin`. It uses a password plus a TOTP one-time code, CSRF protection, and writes an audit log entry for every change.

### Flutter app

- Feature-first layout under `mobile/lib` (`app/`, `core/`, `features/`), as in CLAUDE.md §4.
- **Riverpod** for all state, **go_router** for navigation with auth-state redirects, **dio** for HTTP with a single-flight token refresh, **flutter_secure_storage** for tokens.
- Typed models written by hand (no code generation step), typed error mapping (offline, maintenance, rate-limited, validation, session expired, server).
- Build flavors **dev / staging / prod**. Each has its own application ID suffix, API URL and AdMob IDs, passed with `--dart-define-from-file`. Nothing secret is in these files.
- Design system: color, type, spacing and radius tokens, glass cards, gradient backgrounds, buttons, inputs, and loading, empty, error and offline states. Motion respects the phone's reduce-animations setting.

## Dependencies

| Area | Package | Why |
|---|---|---|
| Backend | fastapi, uvicorn | HTTP API |
| | sqlalchemy[asyncio], asyncpg, alembic | Database access and migrations |
| | redis | Rate limits, CAPTCHA |
| | argon2-cffi | Password hashing (Argon2id) |
| | cryptography | AES-GCM encryption for bank numbers and bot tokens |
| | httpx | Telegram Bot API client |
| | jinja2, python-multipart | Admin panel and referral landing page |
| | pyotp | Admin TOTP |
| | pytest, pytest-asyncio | Tests |
| Flutter | flutter_riverpod | State management |
| | go_router | Navigation |
| | dio | HTTP |
| | flutter_secure_storage, shared_preferences | Tokens / non-sensitive preferences |
| | intl | INR and Indian-number formatting (₹1,15,000) |
| | share_plus, url_launcher, app_links | Sharing, opening Telegram, deep links |
| | google_mobile_ads | AdMob, behind an `AdsService` interface |
| | package_info_plus | App version for update prompts |

## Build system

- `backend/`: `pyproject.toml`, Alembic, a Dockerfile and `docker-compose.yml` (API, worker, Postgres, Redis).
- `mobile/`: a standard Flutter project with Android product flavors. Release signing comes from `key.properties`, which is never committed.
- CI: a GitHub Actions workflow runs backend tests against real Postgres and Redis, then `flutter analyze`, `flutter test` and `flutter build apk --release`, and uploads the APK as a build artifact.

## Spec contradictions and gaps, and how they're resolved

| Topic | Resolution |
|---|---|
| Four paid levels (§8) vs agreed decisions | One paid level at ₹200. Levels 2–4 are counted with ₹0, enforced by `CHECK` constraints. |
| Seeded member count (§11) | Removed. The counter is the real number of verified users. |
| "Offline APK" | Means installable without a store. The app needs internet and shows a clear offline screen. |
| 100 bots all admins in the channels | Every admin bot would receive every join request (100× duplicate webhooks). Only one watcher bot needs to be a channel admin, and the verifier bots don't. |
| Pending join request vs membership | Configurable rule `accept_pending_join_requests` (default on, because requests aren't auto-approved). The record stores which state satisfied each channel. |
| Cancelled join requests | Telegram sends no update when a request is cancelled. Verification is a point-in-time check, and this is documented. |
| Referral link opened *before* install (side-loaded APK) | There's no Play Install Referrer for side-loaded APKs. The landing page shows the code and offers a copy button, and the app pre-fills the code from the link or a user-initiated paste. The server binds the referral only at signup. |
| Signed referral token (§35) | Codes are public by design, so a signature adds nothing. The server validates the code at signup, which blocks unknown, suspended and self codes. |
| "Paid on 31 December" vs the withdrawal flow in §13 | Balances unlock on the payout date. Users then request payment, and the admin pays out in batches with the full status lifecycle. **This is an assumption; see below.** |
| Promotional allocation (§10) | Shown only if the admin records funding into the promotional pool account. The displayed figure is the ledger amount, and rewards stop when the pool runs out. |
| Four-level income in snapshots | The snapshot keeps all four income columns, as requested. Columns 2–4 have `CHECK (= 0)`. |
| `POST /v1/referral/share-token` | Replaced by `GET /v1/referral/share`, because codes are static and nothing needs to be minted. |

## Security-sensitive operations

Signup, login, token refresh, CAPTCHA, verification sessions, Telegram webhooks, contact matching, referral binding, reward crediting, the payout-date unlock, bank-detail changes, withdrawal creation, admin login, admin payout export and marking, bot token storage, and campaign configuration changes. Each one gets rate limits, idempotency or uniqueness where money or identity is at stake, an audit log entry, and a test (CLAUDE.md §25).

## Implementation plan

| Phase | Deliverable |
|---|---|
| 2 — Architecture | `docs/API.md` (every endpoint), `docs/DATABASE.md` (tables, constraints, indexes), navigation map, design tokens |
| 3 — Design system | Flutter theme and reusable widgets |
| 4 — Core flows | Backend services and endpoints, then Flutter screens: signup, login, verification, home, referrals, wallet, withdrawal, profile, sharing |
| 5 — Security | Abuse-case tests from §25 |
| 6 — Performance | Seeded benchmark of the referral, snapshot and wallet queries |
| 7 — Testing | Backend pytest, Flutter unit and widget tests, flow tests |
| 8 — Release | `flutter analyze`, `flutter test`, `flutter build apk --release`, CI, README and release docs |

## Assumptions (please confirm or correct)

1. **Payout flow.** From 31 December users tap *Withdraw*, and Future Fashion pays the requests in batches. The alternative is to pay everyone automatically on 31 December without a request.
2. **Minimum withdrawal** is ₹200, which is one reward. It's configurable.
3. **Verification rule.** A pending join request counts as joining, because requests aren't auto-approved.
4. **Signup with a number that has an unverified account** replaces that account. Pending accounts also expire after 24 hours, so nobody can reserve someone else's number.
5. **App ID and domain** are placeholders (`com.futurefashion.app`, `futurefashion.example`) until you give the real ones. The app ID can't change after the first public release.

## Potential blockers

These are things only Future Fashion can provide. None of them block development.

- Registered company name, address and support contact for the terms and privacy pages. A lawyer should review the reward terms before launch.
- An accountant should confirm the tax treatment of reward payouts.
- A domain with HTTPS for the API and the referral links, and a server to host it.
- Telegram channels, one watcher bot and the verifier bots, created in Telegram with @BotFather.
- An AdMob account and ad unit IDs. Test IDs are used until then.
- A release signing key, kept safe. Losing it means users can't update the app.
- Real Android phones to test APK sharing, deep links and ads.

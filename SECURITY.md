# Security

How the Future Fashion app and server protect users and their money, the
security checklist from `CLAUDE.md` §24, the two database roles, and the map
of every abuse case in §25 to where it is handled and tested.

Report a vulnerability privately to the support address in the app, not in a
public issue.

## Principles

- The server is the only authority for money, verification, counters and
  eligibility. The app shows what the server says and never computes a balance.
- Money is integer paise in a double-entry ledger. Every balance change is a
  balanced transaction; the ledger and audit log are append-only, enforced by
  database triggers.
- Secrets never ship in the APK. Bank numbers, bot tokens and admin 2FA secrets
  are encrypted at rest (AES-256-GCM); phone numbers and account numbers are
  fingerprinted with a keyed HMAC for lookups.

## Two database roles (least privilege)

The app does not connect to PostgreSQL as the owner or a superuser.

- **Owner** (`futurefashion`): owns the tables. Used only by the `migrate`
  step to run Alembic and to create the app role.
- **App role** (`futurefashion_app`): `LOGIN`, `NOSUPERUSER`, `NOCREATEDB`,
  `NOCREATEROLE`, with only `SELECT, INSERT, UPDATE, DELETE` on the tables and
  `USAGE, SELECT` on the sequences. The API and worker connect as this role.

`python -m app.cli ensure-app-role` (run before every migration by the
`migrate` service) creates or refreshes the role and its grants, and sets
default privileges so tables a new migration creates are covered automatically.
The role cannot `DROP`, `ALTER`, or `CREATE` anything, cannot read other roles'
secrets, and cannot bypass the append-only triggers. Verified: it runs the full
app (signup through withdrawal) while `DROP TABLE` and `CREATE TABLE` are
refused.

Set `APP_DB_PASSWORD` in `.env` (see [docs/SETUP.md](docs/SETUP.md)). In local
development and tests the connection in `FF_DATABASE_URL` is used as is.

## Checklist (CLAUDE.md §24)

### Client

- [x] Tokens in `flutter_secure_storage` (Keystore-backed), never in plain prefs.
- [x] No secrets in the APK — verified by scanning the release build ([docs/PENTEST.md](docs/PENTEST.md)).
- [x] HTTPS only in staging/prod: `cleartextTrafficPermitted="false"`, system certificates.
- [x] Release build is not debuggable; `allowBackup=false`; minimal own permissions.
- [x] No sensitive values in logs or analytics; bank numbers masked in the UI.
- [x] Root/jailbreak posture: defence in depth only, never the sole control.

### Server

- [x] TLS terminated at Caddy; real client IP taken only from Cloudflare's ranges.
- [x] Argon2id password hashing; passwords never returned to the client.
- [x] Opaque session tokens stored as SHA-256 hashes; 15-minute access, 30-day
      refresh with rotation; reusing a rotated refresh token revokes the family.
- [x] Request validation with Pydantic; parameterised SQL only (SQLAlchemy).
- [x] Rate limits per IP, phone, account and session (Redis).
- [x] Admin: separate login, TOTP 2FA, CSRF tokens, CSP, `X-Frame-Options: DENY`,
      cookie scoped to `/admin`; every change audit-logged.
- [x] Idempotency keys on every money or identity mutation.
- [x] Secrets from the environment/secrets manager; encrypted sensitive data.
- [x] Least-privilege database credentials (above).
- [x] Errors never expose stack traces, SQL or internal IDs; each carries a request id.
- [x] Security headers on every response: `X-Content-Type-Options: nosniff`,
      `Referrer-Policy: no-referrer`.

### Privacy

- [x] A user sees only their own data; the level-1 list shows masked contacts only.
- [x] No endpoint takes another user's id; no full referral tree is exposed.
- [x] Bank numbers stored encrypted, shown masked (`XXXX XXXX 4821`).
- [x] Internal database ids and infrastructure details are never returned.

## Abuse cases (CLAUDE.md §25)

Each case maps to the test that proves it. Backend tests are in `backend/tests/`;
app tests in `mobile/test/`. `security/probe.py` re-checks the HTTP-facing ones.

| # | Case | Where it's handled / tested |
|---|---|---|
| 1 | Self-referral | DB `not_self_referred` + `test_referrals::test_referrer_cannot_be_changed` |
| 2 | Circular referral | Referrer must pre-exist and be verified → cycles impossible; same test |
| 3 | Same phone reused | `test_auth::test_same_phone_signup_rate_limited`, unique `phone` |
| 4 | Same device / account abuse | `test_risk` (shared bank account, referral-burst flags hold payouts) |
| 5 | Duplicate signup request | `test_auth::test_duplicate_signup_request_creates_one_account` |
| 6 | Duplicate verification callback | `test_verification::test_duplicate_verification_callback_counts_once` |
| 7 | Duplicate reward credit | `test_referrals::test_reward_is_credited_once`, unique `(source_user_id, level)` |
| 8 | Duplicate withdrawal request | `test_wallet::test_duplicate_withdrawal_request` |
| 9 | Login brute force | `test_auth::test_login_brute_force` (CAPTCHA then lockout) |
| 10 | CAPTCHA replay | `test_auth::test_captcha_is_single_use` |
| 11 | Expired Telegram verification | `test_verification::test_expired_link` |
| 12 | Telegram phone mismatch | `test_verification::test_phone_mismatch_then_limit` |
| 13 | Join request pending | `test_verification::test_pending_requests_can_be_required_to_be_approved` |
| 14 | Telegram user already joined | `test_verification::test_already_joined_member_counts` |
| 15 | User cancels Telegram request | `test_verification::test_join_request_missing` |
| 16 | User changes Telegram account | `test_verification::test_switching_telegram_account` |
| 17 | Referral code tampering | `test_auth::test_invalid_referral_code`; referrer fixed at signup |
| 18 | Client modifies reward amount | Server sets every amount; `test_referrals`, `test_wallet` |
| 19 | Client modifies wallet amount | Wallet is backend ledger state; `test_wallet` |
| 20 | Client modifies withdrawal amount | `test_wallet::test_withdrawal_rules` |
| 21 | API replay | `test_auth` (refresh reuse) + `test_wallet` (idempotent) |
| 22 | Concurrent withdrawal | `test_wallet::test_concurrent_withdrawals` (one active per user) |
| 23 | Concurrent reward creation | `test_referrals::test_reward_is_credited_once` |
| 24 | Stale referral snapshot | `test_referrals::test_stale_snapshot_is_refreshed_by_the_worker` |
| 25 | Network loss during signup | `test_auth` idempotent replay |
| 26 | Network loss during withdrawal | `test_wallet` idempotent + app safe-retry (`flows_test`) |
| 27 | App killed during verification | `test_verification::test_reopening_returns_same_session` / `test_expired_link` |
| 28 | App reinstall | `test_auth::test_reinstall_keeps_the_account_and_referrer` |
| 29 | Referral link before install | `test_admin_web::test_landing_page_and_download` |
| 30 | Referral link after install | Same + app (`flows_test`, `screens_test`); code also built into a shared APK |
| 31 | Invalid referral code | `test_auth::test_invalid_referral_code` (404) |
| 32 | Expired campaign | `test_referrals::test_paused_or_ended_campaign_pays_nothing` |
| 33 | Campaign paused | Same test |
| 34 | Server maintenance | `test_admin_web::test_maintenance_mode` + app maintenance screen |
| 35 | Ad unavailable | App: `flows_test` "ads that are unavailable leave no gap" |
| 36 | Telegram bot unavailable | `test_verification::test_no_healthy_bot` / `test_session_moves_off_a_failed_bot` |
| 37 | One bot rate-limited | `test_verification::test_rate_limited_bot_is_skipped` |
| 38 | Multiple bots unavailable | `test_verification::test_no_healthy_bot` |
| 39 | Database temporarily unavailable | `test_admin_web::test_database_outage_is_a_clean_503` |
| 40 | Queue backlog | `test_jobs` (bounded batches, backoff, no double processing) |

## Before handling real money

- [ ] Fill in the registered legal name, address and support contact; have a
      lawyer review the reward terms and an accountant the tax treatment.
- [ ] Generate fresh `FF_DATA_ENCRYPTION_KEY` and `FF_HMAC_KEY`, and store the
      passwords and signing key in a secrets manager with backups.
- [ ] Set `FF_ANDROID_CERT_SHA256` from the real signing key (App Links).
- [ ] Independent penetration test against staging.
- [ ] Load test at campaign scale ([docs/PERFORMANCE.md](docs/PERFORMANCE.md)).
- [ ] Confirm Cloudflare's published IP ranges in `backend/Caddyfile`.

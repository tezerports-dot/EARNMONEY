# API contract (v1)

The app talks only to these endpoints. The server is authoritative for every value in them. The backend implements this file, and the Flutter client in `mobile/lib/core/api` mirrors it.

## Conventions

| Topic | Rule |
|---|---|
| Base URL | `https://<api-host>/v1`, set per build flavor |
| Format | JSON, UTF-8, `snake_case` |
| Auth | `Authorization: Bearer <access_token>` |
| Money | Integer paise in fields ending `_paise`. ₹200 = `20000`. Never floats. |
| Time | RFC 3339 UTC, for example `2026-12-31T18:30:00Z`. The app shows it in IST. |
| Identifiers | Only `public_id` values (8 characters, for example `7Q2K9MXA`) and prefixed references (`TX-…`, `WD-…`). Database IDs are never exposed. |
| Request ID | Every response has `X-Request-ID`. Errors include it so support can trace a problem. |
| App version | The app sends `X-App-Version: 1.0.0`. Below `min_app_version` the server answers `426 UPGRADE_REQUIRED`. |
| Caching | `GET /v1/config` has `Cache-Control: public, max-age=30`. Everything else has `no-store`. |
| Pagination | `?limit=20&cursor=<opaque>` returns `{"items": [...], "next_cursor": "…" or null}`. The maximum limit is 50. |

### Idempotency

Endpoints marked **idempotent** need an `Idempotency-Key` header (a UUID the app generates once per user action and reuses on retries).

- The same key and the same body within 24 hours returns the stored response, with no second effect.
- The same key with a different body returns `409 IDEMPOTENCY_KEY_REUSED`.
- A request that is still running under that key returns `409 REQUEST_IN_PROGRESS`, which the app treats as retryable.

### Errors

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many attempts. Try again in a few minutes.",
    "request_id": "01J8Z6…",
    "retry_after_seconds": 300,
    "fields": null
  }
}
```

`message` is safe to show to users. It never contains stack traces, internal IDs, bot details or whether a phone number exists.

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `VALIDATION_FAILED` | `fields` maps field → message |
| 400 | `CAPTCHA_REQUIRED` | Solve a CAPTCHA and resend |
| 400 | `CAPTCHA_INVALID` | Wrong, expired or already used CAPTCHA |
| 400 | `REFERRAL_CODE_INVALID` | Unknown code, or the code's owner can't refer |
| 401 | `UNAUTHENTICATED` | Missing or invalid access token (the app refreshes once, then logs out) |
| 401 | `SESSION_EXPIRED` | Refresh token expired, revoked or reused |
| 401 | `INVALID_CREDENTIALS` | Wrong phone or password (the same message for both) |
| 403 | `ACCOUNT_NOT_VERIFIED` | The endpoint needs a verified account |
| 403 | `ACCOUNT_SUSPENDED` | Account suspended by an admin |
| 404 | `NOT_FOUND` | |
| 409 | `PHONE_UNAVAILABLE` | Can't sign up with this number (try logging in) |
| 409 | `ALREADY_VERIFIED` | |
| 409 | `IDEMPOTENCY_KEY_REUSED`, `REQUEST_IN_PROGRESS` | See above |
| 409 | `WITHDRAWAL_IN_PROGRESS` | One withdrawal at a time |
| 409 | `BANK_DETAILS_LOCKED` | Can't change bank details while a withdrawal is being paid |
| 422 | `SIGNUPS_CLOSED`, `PAYOUTS_NOT_OPEN`, `BANK_DETAILS_REQUIRED`, `INSUFFICIENT_BALANCE`, `BELOW_MINIMUM` | Business rule |
| 426 | `UPGRADE_REQUIRED` | App too old, and the response includes the download URL |
| 429 | `RATE_LIMITED` | With the `Retry-After` header |
| 500 | `INTERNAL_ERROR` | Generic message only |
| 503 | `MAINTENANCE` | With `message` and the expected end time when known |
| 503 | `VERIFICATION_UNAVAILABLE` | No healthy verification bot right now |
| 503 | `SERVICE_UNAVAILABLE` | Database or Redis unavailable |

### Client retry policy

- `GET`: up to 2 retries with backoff (1 s, 3 s, plus jitter) on network errors, 502, 503 or 504. Never on 4xx.
- Mutations: retried only on network errors, 502, 503 or 504, and only with the same `Idempotency-Key`. Non-idempotent mutations such as login are not retried automatically.
- `429`: wait for `Retry-After`.

## Endpoint summary

| Method | Route | Auth | Idempotent | Rate limit (default) |
|---|---|---|---|---|
| GET | `/v1/config` | none | — | 120/min per IP |
| GET | `/v1/captcha` | none | — | 20/min per IP |
| GET | `/v1/referral-codes/{code}` | none | — | 30/min per IP |
| POST | `/v1/auth/signup` | none | **yes** | 3/hour per phone, 30/hour per IP |
| POST | `/v1/auth/login` | none | — | CAPTCHA after 3 failures, lock after 10 failures/hour per phone, 60/min per IP |
| POST | `/v1/auth/refresh` | refresh token | — | 30/min per session |
| POST | `/v1/auth/logout` | any | natural | — |
| GET | `/v1/me` | any | — | 120/min per user |
| POST | `/v1/telegram/verification-session` | pending | natural | 10/day per user |
| GET | `/v1/telegram/verification-session` | pending or verified | — | 60/min per user |
| GET | `/v1/dashboard` | verified | — | 120/min per user |
| GET | `/v1/referrals/summary` | verified | — | 120/min per user |
| GET | `/v1/referrals/direct` | verified | — | 120/min per user |
| GET | `/v1/referral/share` | verified | — | 120/min per user |
| GET | `/v1/wallet` | verified | — | 120/min per user |
| GET | `/v1/wallet/entries` | verified | — | 120/min per user |
| GET | `/v1/bank-details` | verified | — | 120/min per user |
| POST | `/v1/bank-details` | verified | **yes** | 5/day per user |
| GET | `/v1/withdrawals` | verified | — | 120/min per user |
| POST | `/v1/withdrawals` | verified | **yes** | 5/hour per user |

"Pending" means `PENDING_VERIFICATION`, and "verified" means `ACTIVE`. Server-only routes (Telegram webhooks, admin panel, landing page, health) are listed at the end.

## Endpoints

### `GET /v1/config`

Public, safe configuration. The app loads it at startup, on resume and when a countdown reaches zero.

```json
{
  "server_now": "2026-09-24T12:00:00Z",
  "company_name": "Future Fashion",
  "min_app_version": "1.0.0",
  "apk_download_url": "https://futurefashion.example/download",
  "maintenance": { "active": false, "message": null, "until": null },
  "campaign": {
    "status": "ACTIVE",
    "starts_at": "2026-09-24T00:00:00Z",
    "ends_at": "2026-12-31T18:29:59Z",
    "brand_reveal_at": "2026-12-20T18:30:00Z",
    "launch_at": "2026-12-30T18:30:00Z",
    "payout_opens_at": "2026-12-30T18:30:00Z",
    "brand_name": null,
    "signups_open": true,
    "rewards_open": true
  },
  "rewards": {
    "levels": [
      { "level": 1, "reward_per_user_paise": 20000 },
      { "level": 2, "reward_per_user_paise": 0 },
      { "level": 3, "reward_per_user_paise": 0 },
      { "level": 4, "reward_per_user_paise": 0 }
    ],
    "min_withdrawal_paise": 20000
  },
  "membership": { "verified_count": 18342, "capacity": 50000000 },
  "promotion": { "allocation_paise": null },
  "announcement": null,
  "ads": {
    "banner_enabled": false,
    "interstitial_enabled": false,
    "rewarded_enabled": false,
    "min_interstitial_interval_seconds": 300
  },
  "links": {
    "terms_url": null,
    "privacy_url": null,
    "support_url": null
  }
}
```

- `campaign.status` is one of `NOT_STARTED`, `ACTIVE`, `PAUSED`, `ENDED`.
- `brand_name` is `null` until `brand_reveal_at`, even when the admin has already entered it.
- `membership.verified_count` is the real count of verified users.
- `promotion.allocation_paise` is the amount recorded into the promotional pool, or `null` when nothing is recorded or the admin hides it.
- `announcement`, when set, is `{ "text": "…", "tone": "info" | "success" | "warning" }`.
- `links.*` are `null` when not configured, and the app then shows the terms bundled in the APK.

### `GET /v1/captcha`

```json
{ "captcha_id": "c_9f2…", "question": "7 + 8 = ?", "expires_in_seconds": 300 }
```

Each CAPTCHA can be tried once, right or wrong. A reused ID returns `CAPTCHA_INVALID`.

### `GET /v1/referral-codes/{code}`

This checks a code before signup. It returns `200 {"valid": true}` or `404 REFERRAL_CODE_INVALID`, and nothing about the owner.

### `POST /v1/auth/signup` — idempotent

```json
{
  "phone": "9876543210",
  "password": "at least 8 characters",
  "referral_code": "7Q2K9MXA",
  "captcha_id": "c_9f2…",
  "captcha_answer": "15"
}
```

- `phone`: an Indian mobile number. The server accepts `+91`, `91` or `0` prefixes and spaces, and stores 10 digits starting with 6–9.
- `password`: 8–128 characters.
- `referral_code`: optional. The server validates it, and it can't be changed later.

`201`:

```json
{
  "user": { "…": "same shape as GET /v1/me" },
  "tokens": {
    "token_type": "Bearer",
    "access_token": "…",
    "access_expires_at": "…",
    "refresh_token": "…",
    "refresh_expires_at": "…"
  }
}
```

The account starts as `PENDING_VERIFICATION`. The app then calls `POST /v1/telegram/verification-session`.

Errors: `VALIDATION_FAILED`, `CAPTCHA_INVALID`, `REFERRAL_CODE_INVALID`, `PHONE_UNAVAILABLE`, `SIGNUPS_CLOSED`, `RATE_LIMITED`.

### `POST /v1/auth/login`

```json
{ "phone": "9876543210", "password": "…", "captcha_id": null, "captcha_answer": null }
```

`200` returns `{ "user": …, "tokens": … }`. A pending user can log in, and the app sends them to verification.

Errors: `INVALID_CREDENTIALS` (the same for an unknown phone and a wrong password, with equal timing), `CAPTCHA_REQUIRED`, `CAPTCHA_INVALID`, `ACCOUNT_SUSPENDED`, `RATE_LIMITED`.

### `POST /v1/auth/refresh`

`{ "refresh_token": "…" }` returns `200 { "tokens": … }`. Refresh tokens rotate, so each can be used once. Presenting an already used refresh token revokes the whole session (possible theft) and returns `SESSION_EXPIRED`.

### `POST /v1/auth/logout`

Revokes the current session and returns `204`. The app also clears its stored tokens. The account isn't affected.

### `GET /v1/me`

```json
{
  "public_id": "7Q2K9MXA",
  "phone_masked": "98XXXXXX10",
  "status": "ACTIVE",
  "referral_code": "7Q2K9MXA",
  "referred_by": "K3M9P2QA",
  "created_at": "2026-09-24T10:00:00Z",
  "verified_at": "2026-09-24T10:06:00Z"
}
```

`status` is one of `PENDING_VERIFICATION`, `ACTIVE`, `SUSPENDED`. `referral_code` is `null` until the account is verified.

### `POST /v1/telegram/verification-session`

It returns the open session if there is one, otherwise it creates one. That makes it safe to call again.

```json
{
  "status": "OPEN",
  "bot_username": "futurefashion_verify_03_bot",
  "deep_link": "https://t.me/futurefashion_verify_03_bot?start=vs_Ab3…",
  "expires_at": "2026-09-24T10:30:00Z",
  "channel_count": 3,
  "issue": null
}
```

Errors: `ALREADY_VERIFIED`, `VERIFICATION_UNAVAILABLE`, `RATE_LIMITED`.

### `GET /v1/telegram/verification-session`

It has the same shape. `status` is one of `OPEN`, `IN_PROGRESS`, `COMPLETED`, `EXPIRED`, `FAILED`. `deep_link` is `null` once the session is no longer open. When there's no session at all it returns `404 NOT_FOUND`.

`issue` tells the app what the user should fix. It's one of these values, or `null`:

| `issue` | Status | Meaning |
|---|---|---|
| `CHANNELS_MISSING` | `IN_PROGRESS` | A required channel has no join request yet (or the request was cancelled) |
| `PHONE_MISMATCH` | `IN_PROGRESS` | The shared Telegram number isn't the signup number |
| `TELEGRAM_ALREADY_LINKED` | `IN_PROGRESS` | That Telegram account already verified another account |
| `PHONE_MISMATCH_LIMIT` | `FAILED` | Too many mismatches. The app starts a new session. |

While the verification screen is visible, the app checks every 5 seconds for at most 10 minutes, and has a manual *Check again* button.

### `GET /v1/dashboard`

This is the data for the home screen. Campaign data comes from `/v1/config`.

```json
{
  "user": { "…": "GET /v1/me" },
  "wallet": { "total_earned_paise": 240000, "pending_paise": 240000, "available_paise": 0 },
  "referrals": { "level_1_count": 12, "level_1_pending_count": 3 },
  "share": { "referral_code": "7Q2K9MXA", "referral_link": "https://futurefashion.example/r/7Q2K9MXA" }
}
```

### `GET /v1/referrals/summary`

This is the four-level table from the daily snapshot (CLAUDE.md §9, §20).

```json
{
  "generated_at": "2026-09-24T02:00:00Z",
  "refresh_pending": false,
  "levels": [
    { "level": 1, "user_count": 12, "reward_per_user_paise": 20000, "total_reward_paise": 240000 },
    { "level": 2, "user_count": 40, "reward_per_user_paise": 0, "total_reward_paise": 0 },
    { "level": 3, "user_count": 95, "reward_per_user_paise": 0, "total_reward_paise": 0 },
    { "level": 4, "user_count": 180, "reward_per_user_paise": 0, "total_reward_paise": 0 }
  ],
  "total_user_count": 327,
  "total_reward_paise": 240000,
  "level_1_pending_count": 3
}
```

- `user_count` counts verified users only. `level_1_pending_count` is live and counts direct referrals still verifying.
- Level 1 `total_reward_paise` is the sum of real reward records, not count × rate.
- A snapshot older than 24 hours is returned as it is with `refresh_pending: true`, and a refresh job is queued. A user's first snapshot is computed immediately.

### `GET /v1/referrals/direct`

Level 1 only, newest first, paginated. Nobody below level 1 is ever listed.

```json
{
  "items": [
    {
      "public_id": "K3M9P2QA",
      "phone_masked": "98XXXXXX10",
      "status": "VERIFIED",
      "joined_at": "2026-09-20T09:00:00Z",
      "verified_at": "2026-09-20T09:04:00Z",
      "reward_paise": 20000
    }
  ],
  "next_cursor": null
}
```

`status` is `VERIFIED` or `PENDING`. `reward_paise` is the real reward for that friend, or `0`.

### `GET /v1/referral/share`

```json
{
  "referral_code": "7Q2K9MXA",
  "referral_link": "https://futurefashion.example/r/7Q2K9MXA",
  "apk_download_url": "https://futurefashion.example/download"
}
```

### `GET /v1/wallet`

```json
{
  "total_earned_paise": 240000,
  "pending_paise": 240000,
  "available_paise": 0,
  "in_withdrawal_paise": 0,
  "withdrawn_paise": 0,
  "payouts_open": false,
  "payout_opens_at": "2026-12-30T18:30:00Z",
  "min_withdrawal_paise": 20000,
  "breakdown": [ { "level": 1, "reward_count": 12, "amount_paise": 240000 } ],
  "recent_entries": [ { "…": "wallet entry" } ]
}
```

- Every figure comes from the ledger.
- Once payouts are open, any pending balance is moved to available as a ledger transaction before the response is built. This is safe to repeat.
- `total_earned_paise` is the sum of reward credits.

A wallet entry looks like this:

```json
{
  "id": "TX-8K2M…",
  "kind": "REFERRAL_REWARD",
  "direction": "CREDIT",
  "amount_paise": 20000,
  "created_at": "2026-09-20T09:04:00Z",
  "counterparty_public_id": "K3M9P2QA"
}
```

`kind` is `REFERRAL_REWARD`, `REWARDS_UNLOCKED`, `WITHDRAWAL` or `WITHDRAWAL_RETURNED`.

### `GET /v1/wallet/entries`

This is the paginated list of wallet entries.

### `GET /v1/bank-details`

```json
{
  "status": "SAVED",
  "account_holder_name": "Ravi Kumar",
  "account_number_masked": "XXXX XXXX 4821",
  "ifsc": "HDFC0001234",
  "updated_at": "2026-09-24T11:00:00Z",
  "locked": false
}
```

When nothing is saved, the response is `{ "status": "NONE" }`. The full account number is never returned.

### `POST /v1/bank-details` — idempotent

```json
{ "account_holder_name": "Ravi Kumar", "account_number": "123456784821", "ifsc": "HDFC0001234" }
```

- Name: 2–100 characters, letters, spaces and `.'-`.
- Account number: 9–18 digits.
- IFSC: 4 letters, `0`, then 6 letters or digits.

It returns the `GET` shape. Errors: `VALIDATION_FAILED`, `BANK_DETAILS_LOCKED`, `RATE_LIMITED`.

### `GET /v1/withdrawals`

This is the paginated list of withdrawals, newest first.

### `POST /v1/withdrawals` — idempotent

`{ "amount_paise": 240000 }` returns `201`:

```json
{
  "id": "WD-3JQ9…",
  "amount_paise": 240000,
  "status": "REQUESTED",
  "bank_account_masked": "XXXX 4821",
  "requested_at": "2026-12-31T05:00:00Z",
  "paid_at": null,
  "bank_reference": null,
  "failure_reason": null
}
```

`status` is one of `REQUESTED`, `PROCESSING`, `PAID`, `FAILED`.

- The server checks that the amount is a positive whole number of paise, at least the minimum and no more than the available balance.
- It moves the amount into withdrawal clearing in one transaction.
- Only one withdrawal can be `REQUESTED` or `PROCESSING` at a time.
- Only the admin can mark a withdrawal `PAID` or `FAILED`. `FAILED` returns the money to the available balance.

Errors: `PAYOUTS_NOT_OPEN`, `BANK_DETAILS_REQUIRED`, `INSUFFICIENT_BALANCE`, `BELOW_MINIMUM`, `WITHDRAWAL_IN_PROGRESS`, `VALIDATION_FAILED`, `RATE_LIMITED`.

## Server-only routes

| Route | Purpose |
|---|---|
| `POST /telegram/webhook/{bot_ref}` | Telegram updates. Rejected unless the `X-Telegram-Bot-Api-Secret-Token` header matches that bot's secret. |
| `GET /r/{code}` | Referral landing page: shows the code with a copy button, the APK download and an *open in app* link. It stores nothing. |
| `GET /download` | Redirects to the configured APK URL. |
| `GET /.well-known/assetlinks.json` | Android App Links verification (fingerprints from configuration). |
| `GET /healthz`, `GET /readyz` | Liveness, and readiness (database and Redis). |
| `/admin/…` | Admin panel. Cookie session with CSRF, password + TOTP. See `docs/ADMIN.md`. |

# Database schema

PostgreSQL 16. Migrations live in `backend/migrations` (Alembic). This file explains the tables and the rules the database itself enforces. The migration is the source of truth for exact column types.

## Rules enforced by the database

| Rule | How |
|---|---|
| Money is never a float | Every amount is `BIGINT` paise. |
| Only level 1 pays | `referral_rewards.level CHECK (level = 1)`. |
| Levels 2–4 income is ₹0 | `referral_snapshots.level_{2,3,4}_income_paise CHECK (= 0)`. |
| A reward is credited once | `UNIQUE (source_user_id, level)` on `referral_rewards`. |
| Balanced ledger | Deferred constraint trigger: each ledger transaction's entries sum to 0 at commit. |
| Ledger is append-only | Triggers reject `UPDATE`/`DELETE` on `ledger_transactions` and `ledger_entries`. |
| No negative balances | `CHECK (balance_paise >= 0)` on every account except the external funding account. |
| Duplicate money operations | `UNIQUE` `ledger_transactions.idempotency_key`. |
| One active withdrawal per user | Partial unique index on `withdrawal_requests (user_id) WHERE status IN ('REQUESTED','PROCESSING')`. |
| One phone, one Telegram account per user | `UNIQUE (phone)`, `UNIQUE (telegram_user_id)`. |
| Referrer can't change or loop | The referrer is written once at signup (closure rows keyed by `(descendant_id, level)`). A user can only be referred by an account that already existed and is verified, so cycles are impossible. |
| Audit log is append-only | Trigger rejects `UPDATE`/`DELETE`. |

## Tables

### Accounts and sessions

**`users`**. `id` (internal only), `public_id` (8 characters, unique, also the referral code), `phone` (10 digits, unique, `CHECK ~ '^[6-9][0-9]{9}$'`), `password_hash` (Argon2id), `status` (`PENDING_VERIFICATION` | `ACTIVE` | `SUSPENDED`), `referrer_id` (nullable, the direct referrer), `telegram_user_id` (unique, set at verification), `pending_expires_at`, `created_at`, `verified_at`, `suspended_at`, `updated_at`.
Indexes: `(referrer_id, created_at DESC, id DESC)` for the level-1 list, and `(pending_expires_at) WHERE status = 'PENDING_VERIFICATION'` for cleanup.

**`auth_sessions`**. One row per issued token pair. Columns: `user_id`, `family_id` (all rotations of one login), SHA-256 hashes of the access and refresh tokens (unique), their expiry times, `rotated_at`, `revoked_at`, `created_at`, `last_seen_at`, `user_agent`. Presenting a rotated refresh token revokes the whole family.

**`admin_users`**, **`admin_sessions`**. Admin accounts with Argon2id password hashes and TOTP secrets encrypted with AES-GCM. Sessions store token hashes, a CSRF token and an expiry.

### Referrals

**`referral_edges`**. A closure table limited to depth 4: `ancestor_id`, `descendant_id`, `level` (1–4), `status` (`PENDING` until the descendant verifies, then `QUALIFIED`), `created_at`, `qualified_at`.
Primary key `(descendant_id, level)`, `UNIQUE (ancestor_id, descendant_id)`. Index `(ancestor_id, level) WHERE status = 'QUALIFIED'` for counts.
When a user signs up with a code, the server inserts one row for the referrer (level 1) plus one row per ancestor of the referrer (levels 2–4), in the same transaction as the user row.

**`referral_rewards`**. `beneficiary_id`, `source_user_id`, `level` (`CHECK = 1`), `amount_paise` (`CHECK > 0`), `campaign_id`, `status` (`CREDITED` | `REVERSED`), `ledger_transaction_id` (unique), `created_at`. `UNIQUE (source_user_id, level)`, index `(beneficiary_id, created_at)`.

**`referral_snapshots`**. The latest daily snapshot per user: `user_id` (primary key), `snapshot_date` (IST date), `level_1_count` … `level_4_count`, `level_1_income_paise`, `level_2_income_paise` … `level_4_income_paise` (each `CHECK = 0`), `generated_at`.

### Money

**`ledger_accounts`**. `kind`, `user_id`, `balance_paise`, `created_at`. `UNIQUE NULLS NOT DISTINCT (kind, user_id)`.

| Kind | Owner | Balance means |
|---|---|---|
| `COMPANY_FUNDING` | system | Money put into the program. Negative by design: it's the external source. |
| `PROMO_POOL` | system | Promotional budget not yet given out. Can't go below 0, so rewards stop when it's empty. |
| `USER_PENDING` | user | Earned, not yet withdrawable (before the payout date) |
| `USER_AVAILABLE` | user | Withdrawable |
| `WITHDRAWAL_CLEARING` | system | Requested withdrawals not yet paid |
| `PAYOUT_SETTLED` | system | Paid out to banks |

**`ledger_transactions`**. `public_id`, `kind` (`FUNDING`, `REFERRAL_REWARD`, `REWARDS_UNLOCK`, `WITHDRAWAL_HOLD`, `WITHDRAWAL_PAID`, `WITHDRAWAL_RETURNED`, `ADJUSTMENT`), `idempotency_key` (unique), `reference_type`, `reference_id`, `created_by`, `memo`, `created_at`.

**`ledger_entries`**. `transaction_id`, `account_id`, `amount_paise` (signed and non-zero; adding it to the account balance gives the new balance), `created_at`. Index `(account_id, id DESC)`.

How money moves:

| Event | Entries |
|---|---|
| Admin records funding | `COMPANY_FUNDING −X`, `PROMO_POOL +X` |
| Friend verifies | `PROMO_POOL −20000`, referrer `USER_PENDING +20000` |
| Payout date reached | `USER_PENDING −b`, `USER_AVAILABLE +b` |
| Withdrawal requested | `USER_AVAILABLE −a`, `WITHDRAWAL_CLEARING +a` |
| Admin marks paid | `WITHDRAWAL_CLEARING −a`, `PAYOUT_SETTLED +a` |
| Admin marks failed | `WITHDRAWAL_CLEARING −a`, `USER_AVAILABLE +a` |

**`bank_accounts`**. One per user: `account_holder_name`, `account_number_ciphertext` (AES-GCM), `account_number_last4`, `account_number_fingerprint` (HMAC-SHA256, to spot one bank account used by many users), `ifsc` (`CHECK ~ '^[A-Z]{4}0[A-Z0-9]{6}$'`), `created_at`, `updated_at`.

**`withdrawal_requests`**. `public_id`, `user_id`, `amount_paise` (`CHECK > 0`), `status` (`REQUESTED` | `PROCESSING` | `PAID` | `FAILED`), a copy of the bank details at request time (so later edits can't redirect an in-flight payout), `hold_transaction_id`, `settle_transaction_id`, `batch_id`, `bank_reference` (UTR), `failure_reason`, timestamps. Indexes: the partial unique index above, `(status, requested_at)`, `(user_id, requested_at DESC)`.

**`payout_batches`**. A group of withdrawals exported together for the bank: `created_by`, `request_count`, `total_paise`, `created_at`.

### Telegram verification

**`telegram_bots`**. `ref` (random slug in the webhook URL), `role` (`VERIFIER` | `WATCHER`), `username`, `telegram_bot_id`, `token_ciphertext`, `webhook_secret_hash`, `enabled`, `health` (`HEALTHY` | `RATE_LIMITED` | `FAILING`), `rate_limited_until`, `consecutive_failures`, `weight`, `last_ok_at`, `last_error_at`, `last_error`.

**`required_channels`**. `title`, `chat_id` (internal, never sent to the app), `invite_link` (a join-request link), `sort_order`, `active`.

**`telegram_verification_sessions`**. `user_id`, `bot_id`, `token_hash` (unique; the start token is derived from the session id with HMAC and never stored), `status` (`OPEN` | `IN_PROGRESS` | `COMPLETED` | `EXPIRED` | `FAILED` | `SUPERSEDED`), `telegram_user_id` (bound on the first `/start`), `channels_confirmed_at`, `mismatch_count`, `failure_reason`, `created_at`, `expires_at`, `completed_at`. Partial unique index: one open session per user.

**`telegram_join_requests`**. `(telegram_user_id, chat_id)` primary key and `requested_at`. Written by the watcher bot. Join requests are never approved automatically.

**`telegram_verifications`**. One per verified user: `telegram_user_id` (unique), `session_id`, `bot_id`, `channel_states` (which channels were satisfied by membership and which by a pending request), `verified_at`.

### Configuration

**`campaigns`**. `name`, `starts_at`, `ends_at`, `brand_reveal_at`, `launch_at`, `payout_opens_at`, `brand_name`, `level_1_reward_paise`, `min_withdrawal_paise`, `capacity`, `signups_open`, `paused`, `show_promo_allocation`, `is_current` (one current campaign).

**`app_settings`**. A single row: company details and links, `min_app_version`, `apk_download_url`, maintenance mode, announcement, ad switches and interval, `accept_pending_join_requests`, `verification_session_minutes`, `max_contact_mismatches`.

**`membership_counter`**. A single row, `verified_count`, incremented in the same transaction that verifies a user. It's never set by hand.

### Operations

**`audit_log`**. Append-only: `actor`, `action`, `target`, `details` (never secrets or full bank or phone numbers), `ip`, `created_at`.

**`idempotency_keys`**. `(scope, key)` primary key, `request_hash`, `response_status`, `response_body`, `created_at`, `expires_at`. Inserted in the same transaction as the effect, so a stored response always matches committed data.

**`jobs`**. `kind`, `payload`, `dedupe_key` (unique), `status` (`QUEUED` | `RUNNING` | `DONE` | `FAILED`), `attempts`, `max_attempts`, `run_at`, `locked_until`, `last_error`, timestamps. Workers claim jobs with `FOR UPDATE SKIP LOCKED`.

**`risk_flags`**. Signals for admin review, never shown to users: `user_id`, `kind` (for example `SHARED_BANK_ACCOUNT`), `details`, `created_at`, `resolved_at`.

## Kept in Redis (not Postgres)

- **Rate limit counters**: keys like `rl:<scope>:<id>` with a TTL.
- **CAPTCHA answers**: `captcha:<id>`, 5-minute TTL, deleted on the first attempt.

## Mapping to the spec's entity list (CLAUDE.md §21)

| Spec | Here |
|---|---|
| `wallet_accounts` | `ledger_accounts` |
| `wallet_ledger` | `ledger_transactions` + `ledger_entries` |
| `verification_bots` | `telegram_bots` |
| `campaign_config`, `ad_config` | `campaigns` + `app_settings` |
| `rate_limit_state` | Redis |

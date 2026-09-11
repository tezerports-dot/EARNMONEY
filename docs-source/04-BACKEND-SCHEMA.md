# Backend Schema Document

PostgreSQL is the system of record.

## users

- `id UUID PK`
- `mobile_e164 TEXT UNIQUE`
- `password_hash TEXT`
- `status ENUM`
- `referral_code TEXT UNIQUE`
- `referred_by_user_id UUID NULL FK users(id)`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`
- `last_login_at TIMESTAMPTZ NULL`

## identity_verifications

- `id UUID PK`
- `user_id UUID UNIQUE FK users(id)`
- `provider TEXT`
- `provider_reference TEXT`
- `status ENUM`
- `verified_at TIMESTAMPTZ NULL`
- `failure_reason_code TEXT NULL`
- `created_at`
- `updated_at`

Never store a full Aadhaar number in this operational table.

## protected_identity

Use a separate encrypted/tokenized storage boundary where legally required.

- `id UUID PK`
- `user_id UUID UNIQUE`
- `identity_token TEXT UNIQUE`
- `masked_identifier TEXT`
- `data_classification TEXT`
- `created_at`
- `updated_at`

## telegram_accounts

- `id UUID PK`
- `user_id UUID UNIQUE FK users(id)`
- `telegram_user_id BIGINT UNIQUE`
- `telegram_username TEXT NULL`
- `contact_verified_at TIMESTAMPTZ NULL`
- `connected_at TIMESTAMPTZ`
- `status ENUM`

## telegram_memberships

- `id UUID PK`
- `user_id UUID FK users(id)`
- `telegram_chat_id BIGINT`
- `chat_type ENUM`
- `status ENUM`
- `join_requested_at`
- `joined_at NULL`
- `left_at NULL`

Unique: `(user_id, telegram_chat_id)`

## referrals

- `id UUID PK`
- `referrer_user_id UUID FK users(id)`
- `referred_user_id UUID UNIQUE FK users(id)`
- `status ENUM`
- `credited_at NULL`
- `rejection_reason_code NULL`
- `created_at`
- `updated_at`

## referral_credits

- `id UUID PK`
- `referrer_user_id UUID`
- `referred_user_id UUID`
- `credit_type TEXT`
- `amount INTEGER DEFAULT 1`
- `source_referral_id UUID`
- `created_at`

Unique on `(referrer_user_id, referred_user_id, credit_type)`.

## verification_challenges

- `id UUID PK`
- `candidate_user_id UUID`
- `subject_user_id UUID`
- `challenge_token_hash TEXT`
- `challenge_type TEXT`
- `status ENUM`
- `expires_at`
- `attempts INTEGER`
- `created_at`
- `completed_at NULL`

Important: `subject_user_id` is never exposed to the candidate.

## applications

- `id UUID PK`
- `user_id UUID`
- `state_preference TEXT`
- `tier_preference TEXT`
- `district_preference TEXT NULL`
- `status ENUM`
- `submitted_at`
- `reviewed_at NULL`

Unique: one active application per user unless configured otherwise.

## vacancies

- `id UUID PK`
- `state TEXT`
- `tier TEXT`
- `title TEXT`
- `post_count INTEGER`
- `salary_monthly_paise BIGINT`
- `status ENUM`

## training_batches

- `id UUID PK`
- `batch_code TEXT UNIQUE`
- `venue TEXT`
- `city TEXT`
- `start_date DATE`
- `end_date DATE`
- `capacity INTEGER`
- `status ENUM`

## training_enrollments

- `id UUID PK`
- `batch_id UUID`
- `user_id UUID`
- `status ENUM`
- `attendance_days INTEGER`
- `created_at`

Unique: `(batch_id, user_id)`.

## audit_logs

- `id UUID PK`
- `actor_user_id UUID NULL`
- `action TEXT`
- `entity_type TEXT`
- `entity_id UUID NULL`
- `metadata JSONB`
- `ip_hash TEXT NULL`
- `created_at TIMESTAMPTZ`

Do not put secrets or full identity values in metadata.

## Key indexes

- users.mobile_e164
- users.referral_code
- users.referred_by_user_id
- referrals.referrer_user_id
- referrals.status
- identity_verifications.status
- telegram_accounts.telegram_user_id
- verification_challenges.candidate_user_id
- applications.status
- audit_logs.entity_type/entity_id

## State-machine principle

Business-critical counters must be derived from authoritative rows or maintained transactionally. Never accept `referral_count` from the browser.

Use database transactions and row-level locking for crediting operations to prevent double counting.

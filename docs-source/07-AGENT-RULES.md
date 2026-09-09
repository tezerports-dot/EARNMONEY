# Agent Rules.md — Claude Code Rules

## Rule 1 — Never Guess Sensitive Requirements

If an identity/KYC, legal, financial, employment or security requirement is unclear, stop and identify the assumption before implementing it.

## Rule 2 — Aadhaar Safety

Never:
- expose full Aadhaar numbers to other candidates;
- expose Aadhaar cards to referrers;
- use Aadhaar number as an internal primary key;
- place Aadhaar numbers in URLs;
- put Aadhaar numbers in logs;
- invent a direct UIDAI API;
- store identity data unnecessarily.

Use the approved identity-verification mechanism and store provider references/status where possible.

## Rule 3 — Referral Integrity

The browser is never authoritative for:
- referral count
- KYC status
- Telegram membership
- application eligibility
- hiring status

All critical state is calculated server-side.

## Rule 4 — Telegram Integrity

Never trust a Telegram username as identity.

Use:
- Telegram user ID
- signed one-time connection state
- server-side account binding
- webhook verification
- membership state reconciliation

## Rule 5 — Privacy

Apply data minimization.

Before adding a new personal-data field ask:
1. Why is it needed?
2. Who can access it?
3. How long is it retained?
4. Can a less sensitive value achieve the same purpose?

## Rule 6 — Security

Never commit:
- API keys
- bot tokens
- database passwords
- JWT secrets
- provider credentials

Use environment variables/secrets manager.

## Rule 7 — Database

All important business rules must be backed by:
- database constraints where possible;
- transactions;
- idempotency;
- server-side validation.

## Rule 8 — API

Every endpoint must define:
- authentication requirement
- authorization requirement
- input schema
- output schema
- error behavior
- rate limit

## Rule 9 — Admin

Admin APIs require explicit RBAC.

Sensitive actions require audit logs.

Examples:
- KYC override
- referral credit override
- application status override
- training attendance correction
- vacancy changes

## Rule 10 — Testing

Do not declare work complete because the code "looks correct".

Run tests.

For business-critical changes include tests for:
- happy path
- duplicate requests
- replay attacks
- unauthorized access
- race conditions
- invalid state transitions

## Rule 11 — UI Honesty

Never use wording such as:
- "Guaranteed job"
- "Guaranteed salary"
- "Government approved"

unless the organization has verified documentary authority for the claim.

Show advertised salary separately from final employment terms.

## Rule 12 — No Destructive Changes Without Approval

Do not delete production data, drop production tables, rotate production secrets or change live integrations without explicit approval.

## Rule 13 — Migrations

Every schema change gets a migration.

Never manually alter production schema as a shortcut.

## Rule 14 — Webhooks

All webhooks must be idempotent.

Store provider event IDs when available.

Reject/replay safely.

## Rule 15 — Logs

Logs may contain:
- request ID
- user UUID
- event type
- timing
- non-sensitive status

Logs must not contain:
- password
- OTP
- session token
- bot token
- full Aadhaar
- raw KYC documents

## Rule 16 — Before Deployment

Run:
- tests
- lint
- typecheck
- build
- migration validation
- dependency audit
- secret scan
- container scan

## Rule 17 — Claude Code Execution Style

Work in small increments.

Before editing:
- inspect repository;
- read relevant docs;
- locate existing implementation;
- avoid unnecessary rewrites.

After editing:
- show changed files;
- explain important behavior changes;
- report test commands and results;
- call out anything not verified.

## Rule 18 — Requirement Conflicts

If a requested feature conflicts with privacy/security requirements, implement the safest equivalent behavior and clearly document the deviation.

## Rule 19 — Production Data

Never create test accounts using real people's identity data.

Use synthetic fixtures.

## Rule 20 — Final Review

Before launch confirm:
- authentication secure
- KYC integration approved
- referral engine race-safe
- Telegram binding works
- private join requests work
- admin RBAC works
- audit logs work
- backups restore
- privacy policy/consent flow reviewed
- employment claims reviewed

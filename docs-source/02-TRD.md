# TRD — Technical Requirements Document

## 1. Recommended Stack

### Frontend
- Next.js + TypeScript
- Tailwind CSS or equivalent design system
- React Hook Form + Zod
- Accessible responsive UI
- PWA-friendly candidate experience

### Backend
- Node.js + TypeScript
- NestJS or Fastify
- REST API; optional WebSocket/SSE for status updates
- Background jobs with BullMQ
- Redis for queues/rate limiting/cache

### Database
- PostgreSQL
- Prisma or Drizzle ORM
- UUID internal primary keys
- Separate encrypted/tokenized identity vault where required

### Infrastructure
- Docker
- Managed PostgreSQL
- Redis
- Object storage for permitted documents
- CDN/WAF
- Secrets manager
- Centralized logs and monitoring

## 2. Security Requirements

- TLS everywhere.
- Argon2id password hashing.
- Secure, HttpOnly, SameSite cookies for browser sessions.
- CSRF protection where cookie authentication is used.
- MFA for admins.
- Rate limiting on signup/login/referral APIs.
- CAPTCHA on signup and abuse-prone endpoints.
- Account lockout/backoff after repeated failed login.
- Strict RBAC.
- Audit every sensitive admin action.
- Encrypt sensitive data at rest.
- Never log passwords, OTPs, Aadhaar numbers, access tokens or raw identity documents.
- Use short-lived signed tokens for Telegram binding and verification challenges.
- Separate PII from operational tables when practical.
- Automated secret scanning in CI.
- Dependency and container vulnerability scanning.

## 3. Identity/KYC Architecture

The system must support a pluggable `IdentityProvider` interface.

Example:
- `startVerification(userId)`
- `getVerificationStatus(referenceId)`
- `handleWebhook(payload)`
- `cancelVerification(referenceId)`

Do not directly integrate a non-authorized Aadhaar endpoint.

Preferred internal model:
`User → IdentityVerification → ProviderReference`

Store only the minimum permitted attributes required by the business process.

## 4. Telegram Integration

Create a Telegram bot as a backend-controlled integration.

Flow:
1. Website generates one-time Telegram connection token.
2. Candidate opens bot with signed start parameter.
3. Bot asks the candidate to share contact.
4. Backend verifies the contact against the candidate's verified account according to the platform's lawful verification design.
5. Backend binds `telegram_user_id` to the platform user.
6. Bot provides private channel/group join actions.
7. Bot receives join-request events.
8. Backend verifies that the requesting Telegram account is the bound account.
9. Bot/admin service approves the join request.
10. Membership status is stored with timestamps.

Do not rely on a Telegram phone number as the only identity proof.

Telegram's Bot API provides join-request objects and approval/decline operations; the bot needs the relevant administrator permissions.

## 5. Referral Engine

Referral URL:
`/signup?ref=ABC123`

Rules:
- Validate referral code.
- Never trust client-submitted referrer ID.
- Store attribution server-side.
- One direct referrer per account.
- Prevent self-referral.
- Detect cycles and suspicious clusters.
- Apply configurable attribution window.
- Referral credit is calculated by a state machine.

Example:
`REFERRED → REGISTERED → IDENTITY_VERIFIED → ELIGIBLE_FOR_CREDIT → CREDITED`

## 6. Verification Challenge Engine

Instead of distributing KYC/Aadhaar records:

1. Generate challenge pool from eligible candidates.
2. Remove the candidate's own referrals from that candidate's challenge pool.
3. Randomly select required challenge count.
4. Generate a short-lived challenge token.
5. Candidate submits the required verification response.
6. Backend checks against protected data.
7. Store only result/status and audit metadata.
8. Challenge expires after a defined period.

The UI should show:
- Challenge number
- Allowed verification information
- Submit action
- Result
- Retry policy

It should never show another person's full Aadhaar card.

## 7. Anti-Abuse

Signals:
- Same device/browser fingerprint across excessive accounts
- Same IP subnet bursts
- Duplicate phone
- Duplicate identity-provider reference
- Referral graph concentration
- Abnormally fast referrals
- Repeated failed verification
- Telegram account reuse
- Disposable/automated behavior
- Admin override frequency

Do not automatically reject solely on a weak signal; route high-risk cases to review.

## 8. API Requirements

### Auth
- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/refresh`
- `POST /auth/password/forgot`
- `POST /auth/password/reset`

### Identity
- `POST /identity/start`
- `GET /identity/status`
- `POST /identity/webhook`

### Telegram
- `POST /telegram/connect`
- `GET /telegram/status`
- `POST /telegram/webhook`

### Referral
- `GET /referrals`
- `GET /referrals/code`
- `GET /referrals/progress`
- `POST /verification-challenges`
- `POST /verification-challenges/:id/submit`

### Applications
- `GET /vacancies`
- `POST /applications`
- `GET /applications/me`

### Training
- `GET /training/batches`
- `POST /training/selection`
- `GET /training/me`

## 9. Observability

Metrics:
- Signup conversion
- Login failure rate
- KYC completion
- Telegram binding success
- Join-request approval latency
- Referral conversion
- Challenge pass rate
- Application conversion
- Training attendance
- Fraud review volume
- API latency/error rate

Alerts:
- Authentication abuse
- Queue backlog
- KYC webhook failure
- Telegram webhook failure
- Database errors
- Elevated 5xx
- Suspicious referral spike

## 10. Testing

- Unit tests
- API integration tests
- PostgreSQL integration tests
- Telegram webhook contract tests
- Identity-provider sandbox tests
- Referral state-machine tests
- Authorization tests
- Rate-limit tests
- Security regression tests
- Load tests
- Disaster recovery test

CI must block deployment on failing tests, type errors, lint errors and critical security findings.

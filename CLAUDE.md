# CLAUDE.md — Referral Launch APK
## Master implementation guide for Claude Code

> **Project status:** Greenfield rebuild from scratch.
>
> **Primary client:** Flutter Android APK.
>
> **Future target:** The same Flutter codebase should remain structurally suitable for Play Store and App Store releases.
>
> **Current distribution:** APK shared directly between users.
>
> **Connectivity:** The app is online-dependent. "Offline APK" means the APK is self-contained/installable without a store, **not** that the service works without internet.
>
> **Important product-integrity rule:** Never implement hidden counters, fabricated scarcity, guaranteed financial outcomes, fake users, fake transactions, fake balances, or misleading claims. Any promotional budget, launch date, membership count, or earning amount shown to users must come from authoritative configuration/data and must be presented accurately. If a business requirement conflicts with this, implement the technically safe/transparent version rather than deceptive behavior.

## Agreed product decisions (24 September 2026)

These override anything later in this file that conflicts with them.

1. **Operator.** The program is run by **Future Fashion**. The company name appears in the app, the terms and the reward rules. The registered legal name, address and support contact must be filled in before release.
2. **One paid level.** A user earns **₹200 (20,000 paise)** for each friend they referred *directly* who completes verification. Nothing else pays.
3. **Levels 2–4 are counted, not paid.** The referral table still shows four levels. Levels 2–4 show real counts with **₹0** per user and ₹0 total. That ₹0 is fixed in server code and enforced by database constraints. It is **not** an admin setting, and the reward engine only ever creates level-1 rewards. Do not add per-level reward rates.
4. **Real numbers only.** The membership counter is the real number of verified users, computed by the server. There are no seeded, inflated or "attraction" numbers, and no admin field that sets the displayed count.
5. **Payout date.** Rewards stay pending until the configured payout date (**31 December 2026**, when the countdown ends). From then, users can request payment of their balance to their saved bank account.
6. **Dates are configuration.** Brand reveal (21 December), launch and payout (31 December) come from server configuration, never from the APK.

---

# 1. Product vision

Build a polished, modern, high-conversion-looking referral/reward application for a fashion-brand launch campaign.

The experience should feel:

- premium
- celebratory
- trustworthy
- simple
- fast
- visually rich
- mobile-first
- easy for a non-technical user
- clearly structured around referral rewards
- suitable for future store distribution

The UI should use tasteful 3D-style illustrations, depth, gradients, glass/soft cards, animated counters, celebratory launch graphics, clean typography, and strong information hierarchy.

Do **not** build a casino-looking, scam-looking, or excessively flashing interface.

Do **not** make financial claims appear guaranteed unless they are actually guaranteed by the program's terms.

All money amounts must be represented as integer paise on the backend. Never use floating-point arithmetic for money.

---

# 2. Non-negotiable engineering principles

## 2.1 Inspect before changing

Before writing code:

1. Inspect the entire repository.
2. Read all existing README/MD/specification files.
3. Inspect `pubspec.yaml`.
4. Inspect Android configuration.
5. Inspect iOS configuration if present.
6. Inspect routing.
7. Inspect API/client architecture.
8. Inspect authentication.
9. Inspect tests.
10. Inspect CI/build configuration.
11. Produce a concise implementation plan.
12. Only then start implementation.

Because this is a greenfield rebuild, old business logic may be deleted, but do not blindly delete files until dependencies are understood.

## 2.2 Never vibe-code

Do not:

- invent APIs
- invent database fields
- invent authentication states
- invent Telegram verification results
- hard-code balances
- hard-code referral counts
- use random numbers as business data
- fake successful API responses
- silently swallow errors
- duplicate business logic in multiple screens
- put secrets in Flutter
- trust client-side calculations
- trust client-provided referral income
- trust client-provided withdrawal amounts
- trust client-provided verification state
- trust client-provided Telegram identity
- use floating point for INR
- expose internal server errors to users
- expose database IDs unnecessarily
- put admin credentials in the APK

## 2.3 Server is authoritative

The APK is a presentation/client layer.

The server is authoritative for:

- authentication
- account status
- referral relationship
- referral income
- wallet balance
- withdrawable balance
- withdrawal history
- bank-account status
- Telegram verification
- campaign configuration
- membership counters
- daily referral-tree snapshots
- fraud/risk state
- rate limits
- eligibility
- audit records

The client may calculate UI-only values, but never authoritative financial values.

---

# 3. Critical clarification: APK is not offline application logic

The APK must contain:

- UI
- assets
- fonts
- animations
- static promotional artwork
- client-side validation
- navigation
- API client
- local secure token storage
- share functionality

The server must contain:

- all persistent user data
- all financial calculations
- referral-tree relationships
- Telegram verification state
- campaign counters
- withdrawal processing
- rate limiting
- anti-abuse logic
- admin configuration

If internet is unavailable, show a proper connection state. Do not pretend the user is verified or that a transaction succeeded.

---

# 4. Recommended Flutter architecture

Use a maintainable feature-first architecture.

Suggested structure:

```text
lib/
  app/
    app.dart
    router.dart
    theme/
      app_theme.dart
      colors.dart
      typography.dart
      spacing.dart

  core/
    api/
    auth/
    errors/
    networking/
    storage/
    security/
    widgets/
    animations/
    formatters/
    constants/

  features/
    onboarding/
    auth/
    home/
    referrals/
    wallet/
    withdrawals/
    profile/
    campaign/
    telegram_verification/
    ads/
    apk_sharing/

  main.dart
```

Use a single consistent state-management approach throughout the app.

Do not mix multiple state-management paradigms without a documented reason.

---

# 5. Authentication flow

## Signup

Signup requires:

1. Indian mobile number.
2. Password.
3. Referral code if supplied.
4. Basic validation.
5. CAPTCHA/challenge where appropriate.
6. Submit signup.
7. Account enters `PENDING_TELEGRAM_VERIFICATION`.
8. User receives a button to continue Telegram verification.
9. Telegram verification is completed through the verification-bot flow.
10. Backend confirms Telegram identity + phone match.
11. Account becomes eligible/approved according to campaign rules.
12. User can log in.

The signup UI must clearly explain that Telegram verification is required.

Do not store passwords in plaintext.

Use a strong password hash on the server.

Do not send password back to the client.

## Login

Login:

- mobile number
- password
- rate limited
- generic error messages
- secure token/session
- refresh/re-authentication strategy

Do not reveal whether a phone number exists through error-message differences.

## Logout

Logout should:

- invalidate/expire client session as appropriate
- clear secure local tokens
- return to authentication screen
- not delete account

---

# 6. Telegram verification architecture

## Main admin bot

There should be a central admin-controlled bot/service responsible for configuration.

The central system should manage:

- verification bot pool
- active/inactive bot status
- channel requirements
- campaign configuration
- rotation
- health status
- rate limits
- verification sessions

The APK must never contain Telegram bot tokens.

## Verification bot pool

Design for approximately 100 verification bots as a configurable pool.

Do not assume 100 bots are mandatory in code.

Store bot configuration server-side.

Each bot can have:

- encrypted bot token
- Telegram bot ID
- username
- health state
- capacity/rate-limit metadata
- assigned verification workload
- channel configuration

Secrets must be stored securely server-side.

Never commit tokens to Git.

## Verification flow

```text
Signup
  ↓
PENDING_TELEGRAM_VERIFICATION
  ↓
Server creates verification session
  ↓
User opens assigned Telegram bot
  ↓
Bot presents required channel buttons
  ↓
User sends join requests
  ↓
Bot verifies required Telegram state
  ↓
Bot requests Telegram contact
  ↓
Telegram contact number is compared with signup phone
  ↓
If match:
    verification succeeds
  ↓
Backend activates account
  ↓
User receives confirmation
```

## Join-request requirement

The campaign may use join-request-based channels.

Important:

- Do not auto-approve join requests.
- Admin-controlled approval remains separate.
- If the product rule treats a valid pending join request as satisfying the user's verification requirement, the verification service must explicitly check that state.
- Do not assume "member" when the Telegram API only confirms a pending request.
- Do not repeatedly request Telegram actions after verification succeeds.

## Telegram contact matching

The user must share their Telegram contact through Telegram's native contact-sharing mechanism.

Compare normalized phone numbers server-side.

Rules:

- Indian numbers only.
- Normalize consistently.
- Never expose the stored phone number in bot responses.
- On mismatch, do not permanently trap the user.
- Give a safe retry/reverification path.
- Rate-limit repeated attempts.

## Post-verification bot behavior

After successful verification:

- mark verification complete
- revoke/expire the verification session
- stop unnecessary bot interaction
- do not allow unlimited command spam
- return generic responses for invalid/expired sessions

The bot should not become a public unrestricted API surface.

---

# 7. CAPTCHA and anti-abuse

Use a lightweight mathematical challenge for appropriate signup/verification endpoints.

Example:

```text
7 + 8 = ?
```

Do not rely on CAPTCHA alone.

Implement:

- IP-based rate limiting
- phone-number-based rate limiting
- account-based rate limiting
- verification-session rate limiting
- Telegram verification attempt limits
- login failure limits
- signup burst limits
- withdrawal rate limits
- referral abuse detection
- device/session anomaly detection where legally and technically appropriate

Never expose:

- internal IP
- database identifiers
- bot assignment details
- bot token
- channel internal IDs
- fraud scores
- rate-limit internals
- stack traces

---

# 8. Referral reward model

One paid level (see the agreed decisions at the top of this file).

Each friend a user refers directly, once that friend completes verification, earns the user:

- Level 1: ₹200
- Level 2: ₹0
- Level 3: ₹0
- Level 4: ₹0

Levels 2–4 are tracked so the referral table can show how far a user's referrals spread. They never generate income. The level-1 amount is campaign configuration; a change applies to new rewards only and is audit-logged. The ₹0 for levels 2–4 is fixed in code.

## Important accounting rule

Do not calculate referral income merely by multiplying visible counts on the client.

The backend should create immutable reward/ledger records.

Example conceptual model:

```text
ReferralEdge
  referrer_user_id
  referred_user_id
  level
  created_at
  status

ReferralReward
  reward_id
  beneficiary_user_id
  source_user_id
  level
  amount_paise
  campaign_id
  status
  created_at
```

Use database transactions/idempotency.

A referral reward must never be credited twice because an API request was retried.

## Maximum depth

Only level 1 pays. Levels 2–4 are counted for display. Nothing deeper than level 4 is tracked.

## Referral relationship

The referral relationship must be immutable after qualification unless an explicit admin correction process exists.

Do not allow users to manipulate their own referrer through the client.

---

# 9. Referral page

Primary purpose:

Show users what their referral network has generated.

Required table:

| Layer | Total Users | Income / User | Total Income |
|---|---:|---:|---:|
| Level 1 | ... | ₹200 | ... |
| Level 2 | ... | ₹0 | ₹0 |
| Level 3 | ... | ₹0 | ₹0 |
| Level 4 | ... | ₹0 | ₹0 |

Under the table, state plainly that only direct referrals (level 1) earn rewards.

## Visibility rules

Level 1:

- expandable
- direct referrals visible
- show allowed contact information only
- show user/reference ID
- never expose private information unnecessarily

Level 2–4:

- show counts only
- do not expose individual users

Never allow a user to enumerate the complete network.

## Daily snapshot

The dashboard referral tree does not need real-time updates.

Each user's aggregate referral dashboard can update once in a 24-hour window.

Store:

```text
ReferralSnapshot
  user_id
  snapshot_date
  level_1_count
  level_2_count
  level_3_count
  level_4_count
  level_1_income_paise
  level_2_income_paise
  level_3_income_paise
  level_4_income_paise
  generated_at
```

The server may distribute refresh jobs according to capacity rather than updating every user simultaneously.

Do not make a "5 million users / 86400" calculation a hard-coded scheduling mechanism.

Use a queue/worker system with:

- concurrency limits
- backpressure
- retry policy
- jitter
- monitoring
- idempotency

---

# 10. Home page

The home page is the campaign/launch experience.

Design goals:

- immediate visual impact
- clear reward explanation
- countdown
- referral CTA
- launch celebration
- trust
- readable financial terms

Sections:

### Hero

Large 3D fashion/celebration visual.

Headline concept:

> "Your Referrals. Your Rewards. Our Big Launch."

Secondary copy should explain the campaign without guaranteeing income.

### Countdown

Countdown to 31 December campaign/launch date.

The actual timestamp must come from server configuration.

Do not hard-code a date that cannot be changed.

### Promotional budget

If the campaign genuinely has a ₹1,000 crore promotional allocation, show:

> "Promotional allocation: ₹1,000 crore"

But only if this figure is authoritative and legally approved.

Do not represent a budget as guaranteed individual earnings.

### Brand reveal

Show:

> "Brand name reveal: 21 December"

The date should be configurable.

### Launch

Show:

> "Launch: 31 December"

### CTA

Primary:

> "Start Referring"

Secondary:

> "How It Works"

---

# 11. Membership counter

The counter starts from the real number of verified users (0 at launch). There is no initial or seeded value.

Campaign capacity (configurable):

```text
5 crore
```

The product must not secretly manipulate this number.

If the counter is a real campaign counter, the server is authoritative.

Show:

- current verified/registered participant count
- progress toward configured campaign capacity
- percentage
- explanatory label

Do not manufacture users to increase urgency.

Do not secretly maintain a different number from what the user sees.

If the business wants a public counter while keeping exact internal numbers private, expose only the intentionally published aggregate, but it must still be truthful.

---

# 12. Wallet page

Show:

- total earned
- available/withdrawable
- pending
- withdrawn
- referral reward breakdown
- recent ledger entries

Example:

```text
Total Earned
₹12,500

Available to Withdraw
₹9,500

Pending
₹3,000
```

Every value comes from backend ledger state.

Do not calculate the wallet from referral counts on the client.

Use paise internally:

```text
12500 INR = 1,250,000 paise
```

---

# 13. Withdrawal page

Required:

- withdrawable balance
- bank details status
- add/update bank details
- withdrawal history
- withdrawal status
- minimum withdrawal amount if applicable
- processing information
- campaign terms

Bank fields should be validated.

Do not store sensitive banking information unnecessarily.

Prefer tokenized/secure storage or a dedicated banking/KYC service where applicable.

Never log:

- full bank account number
- sensitive credentials
- OTPs
- passwords

Mask bank information in the UI.

Example:

```text
XXXX XXXX 4821
```

Payout date: every reward stays pending until the configured payout date (31 December 2026). Withdrawal requests open on that date.

Withdrawal lifecycle:

```text
REQUESTED
  ↓
UNDER_REVIEW / PROCESSING
  ↓
PAID
```

Failure:

```text
FAILED
```

Do not allow the client to mark a withdrawal as paid.

---

# 14. APK sharing and referral sharing

The app should have a prominent referral/share section.

User sees:

- referral code
- referral link/deep link
- "Share App + Referral"
- "Copy Referral Code"
- "Share Referral Link"

The requested experience is that a user can share the APK directly.

Important implementation reality:

An installed Android application cannot reliably transmit its own APK binary to another device purely from a normal Flutter API call without handling Android package/file access and sharing permissions correctly.

Implement this safely:

1. Package the distributable APK as a controlled release artifact.
2. Provide a server/CDN-controlled APK distribution URL or an installed-file share mechanism where supported.
3. Share the referral deep link alongside the APK.
4. The referral code must survive installation and first launch.
5. Never put referral attribution solely in local mutable storage.
6. Server validates/refuses self-referral and conflicting attribution.

If direct APK file sharing is implemented, test on real Android versions and avoid broad storage permissions.

The preferred referral flow:

```text
User A taps Share App + Referral
       ↓
APK/share package + referral link/code
       ↓
User B installs
       ↓
App reads referral attribution
       ↓
Signup
       ↓
Referral is bound server-side
```

Do not trust an arbitrary referral code sent in a client request without server validation.

---

# 15. Ads and monetization

Integrate Google AdMob through a dedicated ads service abstraction.

Possible placements:

- banner on selected non-critical screens
- interstitial at controlled navigation boundaries
- rewarded ad only where the product experience genuinely benefits from it

Do not:

- show ads during financial confirmation
- interrupt withdrawal submission
- show misleading ads as buttons
- cause accidental clicks
- flood the home page
- show interstitials on every screen transition

Use remote/configurable frequency caps.

Example:

```text
minimum_interstitial_interval_seconds
banner_enabled
rewarded_enabled
```

Never hard-code production ad IDs into business logic.

Use environment/build configuration.

Respect platform ad policies and consent requirements.

---

# 16. UI/UX system

Use a reusable design system.

## Visual language

Preferred:

- premium 3D hero illustrations
- deep layered backgrounds
- soft glow
- glass/gradient cards
- rounded 20–28px cards
- large typography
- subtle motion
- animated progress
- celebratory confetti around launch moments
- clean INR formatting
- strong CTA buttons
- accessible contrast

Avoid:

- clutter
- 10+ simultaneous animations
- fake notification popups
- flashing "urgent" banners
- fake user activity
- fake earning alerts
- tiny text
- excessive gradients
- misleading buttons

## Animation

Use animations for:

- counters
- page transitions
- card entrance
- progress bars
- referral tree expansion
- campaign countdown
- success states

Animations must not block interaction.

Respect reduced-motion/accessibility settings where possible.

---

# 17. Required screens

Minimum screens:

```text
1. Splash
2. Onboarding
3. Login
4. Signup
5. Telegram verification instructions
6. Home
7. Referral dashboard
8. Referral Level 1 expandable list
9. Wallet
10. Withdrawal / Bank details
11. Withdrawal history
12. Profile
13. Settings
14. Campaign / How it works
15. Share & Refer
16. Verification pending
17. Verification success
18. Error/offline state
19. Maintenance state
20. Terms
21. Privacy
22. Reward/campaign rules
```

---

# 18. Navigation

Recommended authenticated navigation:

```text
Home
Referrals
Wallet
Profile
```

Secondary routes:

```text
Withdraw
Bank Details
Withdrawal History
How It Works
Campaign Rules
Share
Settings
Support
```

Do not put every feature in bottom navigation.

---

# 19. API contract discipline

Before implementing screens, define typed API contracts.

Every API endpoint needs:

- method
- route
- request schema
- response schema
- authentication requirement
- rate limit
- idempotency behavior
- error codes
- cacheability
- retry policy

Example:

```text
GET /v1/dashboard
GET /v1/referrals/summary
GET /v1/referrals/direct
GET /v1/wallet
GET /v1/withdrawals
POST /v1/withdrawals
POST /v1/bank-details
POST /v1/referral/share-token
POST /v1/telegram/verification-session
POST /v1/auth/signup
POST /v1/auth/login
POST /v1/auth/logout
```

Do not invent backend routes while implementing UI.

Create an API contract first.

---

# 20. Daily-update architecture

The user dashboard can be refreshed at most once during the configured 24-hour snapshot window unless an operation explicitly requires fresher data.

Suggested:

```text
User opens dashboard
        ↓
API checks latest snapshot
        ↓
If fresh:
    return snapshot
If stale:
    enqueue refresh
    return latest available snapshot + refresh status
```

Do not make millions of synchronous requests hit referral-tree queries simultaneously.

Use:

- job queue
- batching
- worker concurrency
- database indexes
- precomputed aggregates
- incremental counters where safe

For 5 million users, design capacity from measured benchmarks, not arithmetic alone.

---

# 21. Database design principles

At minimum, conceptual entities:

```text
users
auth_sessions
referral_edges
referral_rewards
referral_snapshots
wallet_accounts
wallet_ledger
bank_accounts
withdrawal_requests
telegram_verification_sessions
telegram_verifications
verification_bots
campaigns
campaign_config
membership_counter
ad_config
audit_log
rate_limit_state
```

Use foreign keys where appropriate.

Use unique constraints for:

- phone number
- referral relationship
- reward idempotency key
- withdrawal idempotency key
- verification session
- transaction/reference identifiers

Create indexes for:

- referrer ID
- referred ID
- beneficiary ID
- reward date
- snapshot user/date
- withdrawal user/status
- verification session token/hash
- login identifiers

---

# 22. Financial ledger

Use double-entry accounting if the reward system becomes financially material.

Do not mutate a balance without a ledger entry.

Conceptually:

```text
Wallet Ledger
  transaction_id
  user_id
  type
  amount_paise
  direction
  reference_type
  reference_id
  idempotency_key
  created_at
```

For each reward:

```text
source/pool account
        ↓
user reward account
```

For withdrawal:

```text
user wallet
        ↓
withdrawal clearing account
```

Every financial operation must be atomic.

---

# 23. Idempotency

All mutation endpoints must support idempotency where duplicate requests can cause financial or identity consequences.

Examples:

```text
signup
verification completion
reward credit
withdrawal creation
bank-details update
referral binding
```

A retry must not create duplicate money.

---

# 24. Security checklist

## Client

- secure token storage
- no secrets
- certificate/network security appropriate to platform
- no debug logging in release
- no sensitive values in analytics
- obfuscation where appropriate
- root/jailbreak detection only as a defense-in-depth measure, never as sole security

## Server

- TLS
- secure password hashing
- session expiration
- refresh-token rotation where used
- request validation
- output encoding
- SQL injection protection
- rate limiting
- CSRF protection where applicable
- audit logging
- secrets manager
- encrypted sensitive data where appropriate
- least-privilege database credentials
- admin MFA
- separate admin endpoints
- monitoring/alerts

## Privacy

Do not expose:

- another user's phone number except where explicitly necessary and authorized
- complete referral-tree identities
- bank account numbers
- internal database IDs
- server infrastructure details

---

# 25. Abuse cases Claude must explicitly test

Before declaring the project complete, test:

1. Self-referral.
2. Circular referral attempts.
3. Same phone used repeatedly.
4. Same device/account abuse.
5. Duplicate signup request.
6. Duplicate verification callback.
7. Duplicate reward credit.
8. Duplicate withdrawal request.
9. Login brute force.
10. CAPTCHA replay.
11. Expired Telegram verification.
12. Telegram phone mismatch.
13. Telegram join request pending.
14. Telegram user already joined.
15. User cancels Telegram request.
16. User changes Telegram account.
17. Referral code tampering.
18. Client modifies reward amount.
19. Client modifies wallet amount.
20. Client modifies withdrawal amount.
21. API replay.
22. Concurrent withdrawal.
23. Concurrent reward creation.
24. Stale referral snapshot.
25. Network loss during signup.
26. Network loss during withdrawal.
27. App killed during verification.
28. App reinstall.
29. Referral link opened before installation.
30. Referral link opened after installation.
31. Invalid referral code.
32. Expired campaign.
33. Campaign paused.
34. Server maintenance.
35. Ad unavailable.
36. Telegram bot unavailable.
37. One verification bot rate-limited.
38. Multiple bots unavailable.
39. Database temporarily unavailable.
40. Queue backlog.

---

# 26. Observability

Implement structured logging.

Track:

- signup success/failure
- verification success/failure
- referral attribution
- reward creation
- withdrawal lifecycle
- API latency
- queue latency
- bot health
- rate-limit events
- error rates

Never log:

- passwords
- bot tokens
- session tokens
- OTPs
- full bank details
- full Telegram contact details

---

# 27. Admin configuration

The admin system should be able to configure without rebuilding the APK:

- campaign start/end
- launch date
- brand reveal date
- promotional allocation
- level-1 referral reward amount (new rewards only)
- payout date
- membership capacity (the counter itself is always computed, never set)
- Telegram bot pool
- required channels
- verification rules
- ad settings
- minimum withdrawal
- maintenance mode
- announcement banners

The APK consumes safe public configuration.

Do not ship secrets or admin controls in the APK.

---

# 28. Release configuration

Use:

```text
dev
staging
production
```

Separate:

- API base URL
- analytics
- AdMob IDs
- app signing
- logging
- feature flags

Production secrets must never be committed.

---

# 29. Testing strategy

Minimum:

### Unit tests

- INR formatting
- referral calculations
- level limits
- referral validation
- authentication state
- countdown calculations
- wallet presentation
- input validation

### Integration tests

- signup
- login
- Telegram verification
- referral attribution
- reward creation
- wallet
- withdrawal
- bank details

### Security tests

- rate limits
- authorization
- IDOR
- replay
- duplicate transactions
- injection
- token expiration

### Flutter UI tests

At minimum:

- signup
- login
- home
- referral dashboard
- wallet
- withdrawal
- logout
- error state

---

# 30. Performance rules

Do not:

- fetch full referral trees
- request all users
- poll every second
- poll every screen
- refresh the wallet continuously
- run expensive database queries from the dashboard
- download unnecessary images
- ship enormous uncompressed assets

Use:

- pagination
- precomputed summaries
- CDN/cache for static assets
- compressed images
- lazy loading
- request cancellation
- local caching for non-sensitive static configuration

---

# 31. UX rules for financial actions

Every financial mutation needs:

```text
Review
  ↓
Confirm
  ↓
Submitting
  ↓
Success / Failure
```

Disable duplicate submission while the request is in flight.

Use idempotency keys.

Never display "Success" until the backend confirms success.

---

# 32. Empty/error/loading states

Every screen must have:

- loading state
- empty state
- error state
- retry action
- offline state where relevant

Do not leave blank white screens.

---

# 33. Copywriting rules

Use persuasive but truthful language.

Allowed style:

> "Invite friends and earn eligible referral rewards according to the campaign rules."

Avoid:

> "Guaranteed ₹10,000 every day."

Avoid fabricated scarcity.

Avoid fake claims such as:

> "Only 3 spots left"

unless the statement is objectively true.

---

# 34. Campaign countdown rules

Countdown should use server time.

Do not trust the phone's clock for campaign eligibility.

The server returns:

```text
server_now
campaign_end
launch_time
reveal_time
```

Client renders countdown.

When countdown reaches zero:

- refresh configuration
- switch UI state
- do not keep showing expired promotion

---

# 35. Deep-link/referral attribution

Referral attribution must survive:

- APK install
- first launch
- signup
- Telegram verification

Use a signed/validated referral token where practical.

Server determines final attribution.

Prevent:

- self-referral
- referral reassignment
- arbitrary referrer changes

---

# 36. Accessibility

Support:

- scalable text
- adequate contrast
- semantic labels
- large tap targets
- screen readers for important controls
- reduced motion where possible

Do not communicate essential information only through color.

---

# 37. Required deliverables

Claude Code must produce:

1. Flutter project.
2. Production-grade folder structure.
3. Design system.
4. All required screens.
5. API client layer.
6. Authentication.
7. Referral UI.
8. Wallet UI.
9. Withdrawal UI.
10. Telegram verification client flow.
11. APK sharing/referral flow.
12. Ad abstraction.
13. Error/loading states.
14. Tests.
15. README.
16. Environment configuration documentation.
17. Build instructions.
18. Release APK build instructions.
19. Security checklist.
20. API contract documentation.
21. Database schema/migration documentation.
22. Admin configuration documentation.

---

# 38. Claude Code workflow

Claude must work in phases.

## Phase 1 — Discovery

Inspect everything.

Output:

```text
Repository state
Architecture
Dependencies
Build system
Existing reusable code
Potential blockers
Implementation plan
```

## Phase 2 — Architecture

Create:

- app architecture
- data models
- API contracts
- navigation
- design tokens

Do not start with random screen-by-screen code.

## Phase 3 — Design system

Build:

- colors
- typography
- spacing
- cards
- buttons
- inputs
- bottom navigation
- dialogs
- loading states
- error states
- 3D illustration placement

## Phase 4 — Core flows

Implement:

1. signup
2. login
3. verification
4. home
5. referral
6. wallet
7. withdrawal
8. profile
9. sharing

## Phase 5 — Security

Implement and test abuse protection.

## Phase 6 — Performance

Benchmark API/database paths.

## Phase 7 — Testing

Run all tests.

## Phase 8 — Release

Build APK.

Verify:

```text
flutter analyze
flutter test
flutter build apk --release
```

Also run Android-specific checks appropriate to the project.

---

# 39. Definition of done

Do not declare completion because "the UI renders."

The project is complete only when:

- app builds
- release APK builds
- authentication works
- referral attribution works
- reward rules work (level 1 pays ₹200; levels 2–4 are counted and pay ₹0)
- wallet is backend-authoritative
- withdrawal is idempotent
- Telegram verification is secure
- rate limits work
- duplicate requests are safe
- referral data is appropriately scoped
- daily snapshot system works
- ads do not break core UX
- deep links work
- APK sharing/referral attribution works
- error states exist
- tests pass
- no secrets are committed
- no debug credentials exist
- no fake financial data exists
- no fabricated counters exist
- documentation exists

---

# 40. Design image generation prompts

Use these prompts to create reference images before implementing each screen. Claude Code should treat the resulting images as visual references, not as a reason to copy inaccessible text or invent assets.

Where a prompt describes four paid levels, follow the agreed decisions instead: level 1 pays ₹200, and levels 2–4 show counts with ₹0.

## Screen 01 — Splash

```text
Create a premium mobile app splash-screen UI for a futuristic Indian fashion-brand referral rewards application. Vertical 9:16 Android screen, luxurious 3D visual language, deep layered background, elegant abstract fashion object, subtle gold and electric accent lighting, floating particles, soft volumetric glow, premium glassmorphism, central temporary brand placeholder, sophisticated typography area, minimal composition, high-end commercial product design, realistic 3D render, clean empty space around the logo, no misleading money imagery, no fake testimonials, no clutter, polished App Store/Play Store quality.
```

## Screen 02 — Onboarding

```text
Design a premium three-panel onboarding mobile UI for an Indian fashion launch referral rewards app. 9:16 portrait. Panel concept: discover the upcoming fashion launch, invite friends, track eligible referral rewards. Use tasteful 3D fashion objects, floating cards, layered depth, elegant gradients, glass cards, celebratory particles, strong CTA button, modern Indian fintech-inspired UX without looking like a bank, clean typography, extremely polished, realistic 3D commercial UI mockup.
```

## Screen 03 — Login

```text
Create a premium Android login screen for a fashion-brand referral rewards application. 9:16 portrait. Luxury 3D background illustration, phone number field, password field, primary Login button, Forgot Password, Signup CTA, subtle referral/campaign visual, glassmorphism card, excellent spacing, high trust, clean typography, accessible contrast, polished production mobile UI, no clutter.
```

## Screen 04 — Signup

```text
Create a premium signup screen for an Indian referral rewards fashion-launch app. 9:16 portrait. Fields for Indian mobile number, password, optional referral code, simple mathematical CAPTCHA, strong Create Account button. Include a clearly designed explanatory card saying Telegram verification is required after signup. Use premium 3D fashion imagery, layered cards, glassmorphism, celebratory but trustworthy visual design, clean commercial app UI.
```

## Screen 05 — Telegram Verification

```text
Create a premium Telegram verification instruction screen inside a mobile referral rewards app. 9:16 portrait. Show a numbered 1-2-3 visual process: open verification bot, complete required channel join requests, share Telegram contact. Use small rounded JOIN 1 / JOIN 2 / JOIN 3 style buttons in the visual reference, not giant links. Include a clear Verify button, Telegram-inspired blue accent used tastefully, 3D shield/verification illustration, security-focused design, no bot tokens or technical details visible.
```

## Screen 06 — Verification Success

```text
Create a premium verification-success mobile screen. 9:16 portrait. Large elegant 3D checkmark/shield, celebratory particles, success card, text hierarchy for "Verification complete" and "Your account is ready", primary Continue button. Premium fashion campaign aesthetic, sophisticated lighting, high trust, polished commercial Android UI.
```

## Screen 07 — Home / Campaign Hero

```text
Create a spectacular premium mobile home screen for a fashion-brand launch referral rewards campaign. 9:16 Android portrait. Hero 3D fashion object, luxurious celebratory atmosphere, large campaign headline, dynamic countdown card to 31 December, campaign launch information, brand reveal date 21 December, referral CTA, campaign allocation information presented as a transparent promotional budget rather than guaranteed individual income. Include a tasteful verified-member counter/progress card. High-end 3D commercial UI, glassmorphism, depth, particles, premium typography, visually exciting but trustworthy.
```

## Screen 08 — Referral Dashboard

```text
Create a premium referral dashboard mobile UI for a four-level referral rewards program. 9:16 portrait. Main visual is a sophisticated 3D network/tree motif. Include a beautiful table with columns Layer, Total Users, Reward/User, Total Reward. Four rows Level 1, Level 2, Level 3, Level 4. Level 1 has an expandable card showing direct referrals; deeper levels show aggregate counts only. Use INR formatting, elegant glass cards, depth, subtle glowing connectors, modern fintech/fashion campaign aesthetic, polished production UI.
```

## Screen 09 — Expanded Level 1

```text
Create a premium mobile UI showing an expanded Level 1 direct-referral list. 9:16 portrait. Use clean cards with masked/allowed contact information and user/reference IDs, status chips, date information where appropriate. Header shows Level 1, total direct referrals and eligible reward summary. Sophisticated 3D background motif, glass cards, excellent hierarchy, privacy-conscious presentation, no unnecessary personal information, high-end app design.
```

## Screen 10 — Wallet

```text
Create a premium wallet screen for a referral rewards application. 9:16 portrait. Large Total Earned card, Available to Withdraw card, Pending card, referral-reward breakdown, recent transaction list, Withdraw button. Use elegant 3D wallet/coin illustration without excessive gambling aesthetics. INR formatting, premium glassmorphism, deep layered background, polished fintech-grade UI, trustworthy and easy to understand.
```

## Screen 11 — Withdrawal / Bank Details

```text
Create a premium withdrawal screen for an Indian referral rewards application. 9:16 portrait. Large withdrawable balance, masked bank account card, Add Bank Details button, withdrawal amount field, Review Withdrawal button, processing-information card. Use sophisticated 3D secure-bank/vault illustration, glass cards, clean INR typography, strong trust signals, privacy-conscious design, polished commercial mobile UI.
```

## Screen 12 — Withdrawal History

```text
Create a premium withdrawal-history mobile screen. 9:16 portrait. Timeline/list cards showing Requested, Processing, Paid, Failed states with dates and INR amounts. Use elegant status icons, subtle 3D financial illustration, clean spacing, premium glass UI, high trust, no clutter.
```

## Screen 13 — Share & Refer

```text
Create a premium referral sharing screen for an Android app. 9:16 portrait. Show the user's referral code, referral link, large Share App + Referral button, Copy Code button, and an attractive 3D smartphone-to-smartphone sharing illustration. Make it clear that the shared installation/link carries the referral attribution. Luxurious fashion-launch campaign visual style, premium glassmorphism, high engagement without deceptive urgency.
```

## Screen 14 — Membership Counter

```text
Create a premium campaign participation counter screen. 9:16 portrait. Large verified-member count, elegant animated-style progress bar toward a configured campaign capacity, percentage indicator, campaign participation explanation. Use 3D crowd/network illustration, premium lighting, glass cards, clean typography. The counter must look like a truthful published campaign statistic, not fabricated scarcity.
```

## Screen 15 — How It Works

```text
Create a premium mobile "How It Works" screen for a four-level referral rewards campaign. 9:16 portrait. Four beautiful 3D numbered steps: create account, complete Telegram verification, invite eligible users, track rewards. Include a visual four-level referral tree. Premium fashion-brand launch style, elegant cards, excellent typography, clear explanatory UX, no exaggerated income promises.
```

## Screen 16 — Profile

```text
Create a premium profile screen for a referral rewards fashion-launch app. 9:16 portrait. User identity card, verification status, referral code, account information, security section, settings, logout button. Use sophisticated 3D fashion-avatar placeholder, glass cards, clean hierarchy, premium commercial UI.
```

## Screen 17 — Settings

```text
Create a premium settings screen for a modern Flutter Android referral rewards app. 9:16 portrait. Account security, notifications, app appearance, privacy, terms, campaign rules, support, logout. Use elegant cards and subtle 3D decorative elements, excellent spacing, premium minimal UI.
```

## Screen 18 — Offline / Connection Error

```text
Create a premium mobile connection-error screen for an online-dependent fashion referral app. 9:16 portrait. Elegant 3D disconnected-network illustration, clear "Connection unavailable" message, Retry button, short explanation that the app requires internet to securely sync account and reward data. Maintain premium visual identity and avoid alarming red-heavy design.
```

## Screen 19 — Maintenance

```text
Create a premium maintenance screen for a fashion launch referral application. 9:16 portrait. Beautiful 3D construction/maintenance illustration, calm message, estimated return time placeholder, Retry button, campaign branding, sophisticated glass UI, reassuring premium aesthetic.
```

## Screen 20 — Launch Celebration

```text
Create a spectacular premium launch-day mobile screen for a fashion brand reveal. 9:16 portrait. Large 3D fashion reveal object, celebratory confetti, cinematic lighting, elegant countdown-complete transition, reveal-date/launch messaging, premium luxury-brand atmosphere, sophisticated gold/electric accents, polished commercial UI, no fake financial claims.
```

---

# 41. Claude Code implementation prompt

Use this after supplying the design-reference images:

```text
You are implementing a production-grade Flutter Android application from scratch.

Read CLAUDE.md completely before touching code.

Do not start coding immediately.

First:
1. Inspect repository.
2. Inspect all documentation.
3. Inspect Flutter/Android versions.
4. Inspect current build configuration.
5. Produce a short architecture and implementation plan.
6. Identify contradictions or missing API contracts.
7. Identify security-sensitive operations.
8. Identify what belongs in the APK versus the server.

Then implement the application according to CLAUDE.md.

Use the supplied screen images as visual references.

Do not simply create static mockups. Build real reusable Flutter widgets.

Do not invent backend behavior.

Where backend APIs are not yet available:
- create typed interfaces/contracts
- create mock repositories only behind interfaces
- clearly label mock implementations
- do not pretend mock data is production financial data

All financial values are backend-authoritative and represented in integer paise.

All referral relationships and reward credits are server-authoritative.

Do not put secrets in the APK.

Do not implement fabricated counters, fabricated users, fake earnings, fake notifications, fake scarcity, or hidden business rules.

Do not expose sensitive user information.

Implement loading, error, empty, maintenance, and offline states.

Use responsive layouts for common Android screen sizes.

Use a coherent design system.

Run:
- flutter analyze
- flutter test
- relevant integration/widget tests
- release build

Fix actual errors rather than suppressing warnings.

Do not use broad ignore rules to make CI green.

Do not remove tests merely because they fail.

Do not downgrade dependencies simply to bypass errors without explaining the compatibility reason.

After each major phase, report:
- files changed
- tests run
- tests passed/failed
- remaining blockers
- assumptions made

At the end provide:
- architecture summary
- screen inventory
- API contract inventory
- security checklist
- test results
- build result
- exact next steps
```

---

# 42. Final Claude Code rule

The goal is not "make the APK look finished."

The goal is:

**Build a maintainable, secure, testable, truthful, production-grade referral campaign application whose Flutter client can later be packaged for Google Play and Apple App Store.**

When a shortcut creates hidden state, duplicate money, security risk, fake information, or an untestable system, do not take the shortcut.

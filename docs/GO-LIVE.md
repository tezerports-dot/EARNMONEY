# Going live

What is ready, what must be done first, and how to deploy. Written against
the state of the repo at the time of the last commit on this branch.

---

## 1. Blockers — the system will not work correctly until these are done

These are not polish. Each one either stops the product working or creates a
real risk.

### 1.1 Set `AADHAAR_HASH_PEPPER` and never rotate it casually

Identity numbers are stored as an HMAC keyed with this pepper. Without it the
API refuses to start, which is deliberate: a plain digest of a 12-digit
number is exhaustible offline in minutes.

Generate 32+ random bytes, store it in the secret manager, **back it up**.
Losing it means no existing account can ever be matched again. Changing it
invalidates every stored hash, so duplicate detection silently stops working.

### 1.2 Configure the real CAPTCHA

`TURNSTILE_SECRET_KEY` must be set. In production the API refuses to boot
without it rather than falling back to a stub that passes everything.

The app currently sends the literal string `'app'` as its captcha token — the
Turnstile widget is not yet wired into the signup form. **Until it is, real
Turnstile will reject every signup from the app.** Either wire the widget or
keep signup on the web build, where the widget can be embedded, until it is
done. This is the one place where the app and the server are not yet agreed.

### 1.3 Configure the identity provider

`IDENTITY_PROVIDER_BASE_URL`, `IDENTITY_PROVIDER_API_KEY` and
`IDENTITY_PROVIDER_WEBHOOK_SECRET`. The API refuses to boot in production
without the base URL. The current implementation is a pluggable interface
with a mock behind it; a real licensed provider has to be connected before
any real candidate's identity is checked.

### 1.4 Telegram

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET`,
both chat ids and both invite links. Verification is the gate on the whole
funnel: a candidate who cannot verify cannot refer, train or apply.

Register the webhook with the secret token — the API rejects any update that
does not carry it.

### 1.5 Replace the AdMob test ids

`app.json` carries Google's public test app id and
`AdBanner.tsx` carries a placeholder unit id. Shipping test ids earns no
revenue; shipping *real* ids in a debug build gets AdMob accounts suspended,
which is why the unit id is chosen by `__DEV__` rather than a flag.

### 1.6 Change the seeded admin password

`prisma/seed.ts` creates `+910000000000 / ChangeMe123!DevOnly` outside
production. Use `npm run create-admin` for the real first admin: it refuses
to run if an admin already exists, refuses to promote a candidate account,
and takes the password from the environment rather than argv, where it would
land in shell history and `ps`.

### 1.7 Legal review under the DPDP Act

Not a code task, and not one to skip. The system collects identity numbers
and links them to phone numbers and referral graphs. Consent, retention,
deletion and breach notification all need a decision before real data is
collected.

---

## 2. Deployment constraints

### 2.1 The website and the API must share a registrable domain

Auth cookies are `SameSite=Lax` (`strict` for the refresh token). A browser
discards a `SameSite=Lax` cookie set by a cross-site response, so if the site
and the API are on unrelated domains **nothing stays logged in** — login
appears to succeed and the next request is a 401.

This was confirmed in a real browser: served from `localhost:8081` against an
API on `127.0.0.1:3399`, no session cookie was stored; moving both to
`127.0.0.1` fixed it with no code change.

    app.bbazaar.com   → the website (static files)
    api.bbazaar.com   → the API
    COOKIE_DOMAIN=.bbazaar.com
    COOKIE_SECURE=true
    CORS_ORIGIN=https://app.bbazaar.com

The Android app is unaffected — it is not a browser and has no site
boundary — but it needs the same `CORS_ORIGIN` to not be wrong for web.

### 2.2 Set `COOKIE_SECURE=true` in production

Without it, cookies travel over plain HTTP if anything ever reaches the API
that way.

### 2.3 Run the worker as its own process

`PROCESS_ROLE=worker npm run start:worker`, in its own container. This is the
architecture's central guarantee — scheduled updates never compete with
signup and login for the same connection pool — and it is structural, not
advisory. Running everything in one process silently gives it away.

Pools are explicit: `DB_POOL_API=10`, `DB_POOL_WORKER=5`. Prisma's default is
`cpus × 2 + 1` **per process**, so four containers on an 8-core box quietly
ask Postgres for ~68 connections and signup starts failing during a routine
fan-out.

---

## 3. Building the two front ends

Both come from `apps/mobile`. One codebase, two targets.

### Website

    cd apps/mobile
    EXPO_PUBLIC_API_BASE_URL=https://api.bbazaar.com/api/v1 npm run build:web

Produces `dist/` — static HTML, JS and CSS, about 380 KB of JavaScript. Any
static host serves it: Cloudflare Pages, Netlify, S3 + CloudFront, or nginx.

It is a single-page app, so the host must rewrite unknown paths to
`index.html` or deep links 404.

### Android APK

    cd apps/mobile
    npm run build:apk      # APK, for direct distribution
    npm run build:aab      # App Bundle, for the Play Store

Both go through EAS Build, which needs an Expo account and a real
`eas.projectId` in `app.json` (currently `REPLACE_WITH_YOUR_EAS_PROJECT_ID`).
Set `EXPO_PUBLIC_API_BASE_URL` in the EAS build profile so the built app
points at production.

This is a genuinely native build, not a WebView wrapper, which is what makes
AdMob work normally.

**Before the first store submission:** bump `versionCode` in `app.json` for
every upload, add the app icon and splash assets (there is no `assets/`
directory yet), and write the Play Store privacy policy — an app handling
identity numbers will be asked for one.

---

## 4. What has been verified

| Area | Coverage |
| --- | --- |
| API unit tests | 155 passing |
| Mobile unit tests | 13 passing |
| Route audit | 65 checks over all 30 endpoints — happy path, 401, 403 by role, CSRF on writes, webhook token rejection, signup rate limit |
| Website in Chromium | 24 checks — boot, signup, login, session cookie, all six screens, nav accessibility, answering a challenge |
| Idempotency | 1,000 concurrent delivery attempts across 50 accounts → exactly 50 deliveries, 0 double-applies, re-proved after a Redis flush |
| Telegram funnel | Forwarded contact rejected, wrong number rejected, public join alone insufficient, private request → ACTIVE |
| Admin authoring | Create with spacing, duplicate 409, bad number 400, last-active retire refused, mid-flight answer edit harmless |
| Production guards | CAPTCHA and identity provider each refuse to boot with a stub |

### What has *not* been verified

- **No APK has been built.** EAS Build needs an Expo account and network
  access this environment does not have. `expo prebuild` generates a coherent
  Android project — correct package, permissions and AdMob app id — but that
  is a config check, not a build.
- **No real Telegram bot, CAPTCHA or identity provider has been contacted.**
  Those paths are tested against the API's own contract, not the vendors'.
- **No load test at scale.** Capacity is calculated and benchmarked on single
  operations (see `docs/SCALE-ARCHITECTURE.md`), not driven at 2.9M accounts.
- **No penetration test.** The security posture is reasoned and unit-tested;
  it has not been attacked by someone trying.

---

## 5. First-day operations

- `audit_logs` is the only unbounded table, roughly 6 GB/year at 2.9M
  accounts. Partition it before 1M accounts, not after.
- Watch `/ops/metrics` (admin only) and the scheduler's tick table. A tick
  that never completes means the dispatcher died mid-slot; recovery re-runs
  it, and delivery is idempotent, so the safe response is to let it.
- The Redis throttler **fails open** by design: if Redis is unreachable,
  requests are allowed rather than everyone being locked out. That is the
  right trade for availability and the wrong one during an attack, so alert
  on Redis being down rather than assuming rate limiting is holding.
- Set the two targets before opening signups
  (`PATCH /admin/config/referral_threshold`,
  `PATCH /admin/config/kyc_challenge_threshold`). They are stored in
  `system_config`, never hardcoded, and changing them takes effect
  immediately for every candidate.
- Add practice numbers before opening training
  (`POST /admin/reading-items`). The bank ships with 10 starter entries;
  candidates cycle through them least-recently-seen first, so a target of 200
  against 10 numbers means each comes round about 20 times. Add more to
  reduce repetition — the bank size does not cap the target.
- Watch the pass rate per item in `GET /admin/reading-items`. An item at 0%
  across many attempts is a mistyped answer, not a hundred candidates
  misreading the same number. This check found a bad entry in the seed data
  before it shipped.

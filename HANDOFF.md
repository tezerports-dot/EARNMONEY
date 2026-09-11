# Handoff — read this first

This repo was built in a chat-based environment (no persistent session)
across several stages. This file is the state at handoff time — read it
before making changes so you don't redo or contradict earlier decisions.

## Read in this order
1. `docs/SPEC-DEVIATIONS.md` — two deliberate changes from the original
   8-file spec, with rationale. Don't "fix" these back to the original
   values without re-reading why they changed.
2. `README.md` — setup, testing, and Hostinger deployment.
3. This file, for exactly what's done vs in-progress below.

## Done, tested, wired into `app.module.ts`
- Auth (signup/login/refresh/logout), RBAC scaffolding, CSRF, rate limiting
- Referral crediting + eligibility engine (3 referrals + 3 KYC challenges,
  both admin-tunable via `system_config`, never hardcoded)
- KYC training challenge engine (synthetic data only — see deviations doc)
- Applications (submit, gated server-side on APPLICATION_ELIGIBLE)
- Identity verification module — **wired in, but only with `MockIdentityProvider`**
  (dev only). Swap the provider in `identity/identity.module.ts` once a real
  vendor is contracted. Note the mock's 5-second timer only flips its own
  in-memory state; `GET /identity/status` reads the database, which advances
  only when a signed `POST /identity/webhook` arrives. In dev, fire that
  webhook yourself — HMAC-SHA256 the raw body with
  `IDENTITY_PROVIDER_WEBHOOK_SECRET` and send it as `x-signature`.

38/38 unit tests passing, lint clean, `npm run build` emits `dist/main.js`,
and the app boots against a real Postgres. Run `npm ci && npx prisma generate
&& npm test && npm run lint && npm run build` from `apps/api` to confirm
before you build on top.

## In progress — NOT wired in, will not compile if you add it as-is
`src/telegram/`:
- `telegram-bot.service.ts` — done, wraps the Telegram Bot API.
- `telegram.service.ts` — done: link-token issuance, `/start` binding,
  `chat_member` / `chat_join_request` webhook handling, calls
  `usersService.markTelegramVerified()` once all `TELEGRAM_REQUIRED_CHAT_IDS`
  show `APPROVED` membership.
- **Missing:** `telegram.controller.ts` (candidate `GET /telegram/link` +
  public `POST /telegram/webhook`, same pattern as `identity.controller.ts`
  — copy its shape, auth-free webhook + secret-token check instead of HMAC,
  since Telegram's `X-Telegram-Bot-Api-Secret-Token` header does that natively)
  and `telegram.module.ts`. Then add `TelegramModule` to `app.module.ts`.
  No tests written yet either — model them on `identity.service.spec.ts`.

## Not started
- **Admin panel** (`src/admin/` exists with an empty `dto/` folder and
  nothing else). Needs: list/filter users (esp. `REVIEW_REQUIRED` /
  `KYC_REJECTED` / `DUPLICATE_REVIEW`), adjust `system_config` thresholds,
  CRUD on `vacancies` and `training_batches`, expand the
  `kyc_training_scenarios` bank, review submitted `applications`. Guard
  everything with `RolesGuard` + `@Roles('ADMIN_...')` — already built,
  just needs to be applied to new controllers.
- **Frontend** — candidate + admin UI. Deliberately deferred to Claude
  Design / a separate Claude Code pass per the project owner's own plan.
- **Real identity/KYC vendor** — do not build Aadhaar verification directly;
  contract a licensed provider and implement `IdentityProvider` (see
  `identity/identity-provider.interface.ts`).
- ~~**The initial Prisma migration**~~ — done. See "Import pass" below.

## Import pass — what changed when this landed in the repo

Generating the Prisma Client (the step the previous environment could not
run) cleared the expected `Role`/`User` import errors, but also surfaced
several defects that only appear once the code is actually compiled and
booted. Unit tests could not catch these: they mock every dependency, so
they never exercise Nest's real dependency-injection graph or the
production build output.

Fixed:

- `prisma/migrations/20260909125114_init/` — generated from `schema.prisma`,
  applied to an empty Postgres 16, and re-verified with `migrate deploy` +
  `db seed` on a fresh database.
- `audit-log.service.ts` — `metadata: Record<string, unknown>` is not
  assignable to Prisma's `InputJsonValue`; now cast to
  `Prisma.InputJsonObject` at the write. This was the one real type error
  hiding behind the "run prisma generate" note.
- `tsconfig.build.json` — added. Without it, `prisma/seed.ts` widened the
  compilation root and `nest build` emitted `dist/src/main.js`, while the
  Dockerfile and `start:prod` both run `dist/main.js`. The production
  container would have crash-looped on first boot.
- `eligibility.module.ts` — now imports `SystemConfigModule`.
  `EligibilityService` injects `SystemConfigService`, which is neither
  `@Global()` nor previously imported, so `AppModule` failed to instantiate.
- `auth.module.ts` — re-exports `JwtModule`. `@UseGuards(JwtAuthGuard)`
  constructs the guard in the *host* module's context, so every module using
  it needs `JwtService` resolvable there.
- `main.ts` — `app.get('ConfigService')` (string token) never resolves;
  changed to `app.get(ConfigService)`.
- `package.json` — added the `prisma.seed` entry that `npx prisma db seed`
  requires (the README and `docker-compose.prod.yml` both document that
  command), and dropped the non-existent `test/**/*.ts` glob from the lint
  script, which made `npm run lint` fail outright.
- `auth.service.spec.ts` — replaced a `require('crypto')` that the ESLint
  config rejects.

Nothing else was changed: no new features, no behaviour changes to the
referral, eligibility, or KYC-training logic.

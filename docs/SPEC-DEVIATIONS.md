# Deviations from the original spec pack

The original spec (01-PRD.md through 07-AGENT-RULES.md) is the reference for
everything except the two points below, which were changed deliberately
after review, before any code was written.

## 1. Referral threshold: 200 → 3 (admin-configurable)

The original PRD set a default of 200 verified referrals before a candidate
becomes eligible to apply. At that number, filling the advertised posts would
require millions of people to complete full identity verification with no
realistic path to a job for the large majority of them — a cost landing
mostly on people who never asked to be part of the process (the referred
contacts). 3 was agreed as the working default. It is stored in
`system_config.referral_threshold`, never hardcoded, and can be changed by an
admin at any time — see `SystemConfigService`.

## 2. KYC "verification challenge" now uses synthetic data, not real applicants

The original spec's anti-fraud mechanic had each candidate complete a
"privacy-preserving verification challenge" against a randomly selected
*real* applicant's protected identity record. Even without exposing raw
documents, this routes real people's government-ID-linked data through
untrained peers as a side effect of someone else trying to get a job — a
privacy and legal exposure that doesn't go away just because the threshold is
lower.

The redesigned version (`KycTrainingScenario` / `ChallengeAttempt` in the
schema, implemented in `src/kyc-training/`) instead uses a bank of synthetic,
fictitious documents that the institute authors and controls — the same way
banks train tellers on dummy documents before they handle real ones. It
tests the same underlying skill (can this candidate correctly spot a
mismatch, an expired document, or a tampered ID?) without any real
applicant's data ever being shown to another candidate.

**Operational implication:** the institute needs to maintain and periodically
expand the scenario bank (`kyc_training_scenarios` table / `prisma/seed.ts`)
so candidates aren't stuck re-seeing the same handful of examples. This
should become an admin-panel feature in a later stage rather than a
seed-file-only workflow.

## Everything else

Follows the original 8 documents as written. If a future change departs from
them again, add it here with the same before/after/why structure, per Agent
Rule 18 in 07-AGENT-RULES.md.

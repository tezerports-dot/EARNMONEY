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

## 2. KYC "verification challenge" is a number-reading test on generated numbers

The original spec's anti-fraud mechanic had each candidate complete a
"privacy-preserving verification challenge" against a randomly selected
*real* applicant's protected identity record. Even without exposing raw
documents, this routes real people's government-ID-linked data through
untrained peers as a side effect of someone else trying to get a job — a
privacy and legal exposure that doesn't go away just because the threshold is
lower. The Aadhaar Act restricts disclosure of identity information to
entities authorised under it, and consent obtained as a condition of getting
a job is not freely given in the sense the DPDP Act requires.

The implemented version (`src/kyc-training/`) shows a **generated** 12-digit
number in Aadhaar format, asks one question about it, and grades the typed
answer against the answer computed from that number. The five question types
are: the full number, its first / middle / last four digits, and how many
times a given digit appears. It measures whether the candidate can read an
identity number accurately, which is the part of the job the test is for.

Numbers are generated per attempt (`number-reading.util.ts`, Verhoeff-valid so
they look real), never taken from an account. Two consequences follow:

- **No content bank to maintain.** Supply is unlimited and every challenge
  carries its own answer, so an admin-set target of 5 or 200 is equally
  reachable and there is nothing to author or expand.
- **Instant, certain grading.** The grader always knows the right answer, so
  no human review and no third-party lookup is involved.

**Superseded:** an earlier iteration used a bank of synthetic documents with a
fault to be identified (`KycTrainingScenario`, `prisma/kyc-scenarios.ts`,
`AdminScenariosService`). It was replaced because it needed content authored
and expanded to stay useful, and graded a judgement call rather than the
reading skill. The table and its admin CRUD remain so existing attempt history
stays readable; nothing issues a `DOCUMENT_REVIEW` challenge any more.

## Everything else

Follows the original 8 documents as written. If a future change departs from
them again, add it here with the same before/after/why structure, per Agent
Rule 18 in 07-AGENT-RULES.md.

# PRD — Job Referral & Hiring Platform

## 1. Product Summary

A recruitment platform for 15,000 advertised positions across Rajasthan, Uttar Pradesh and Gujarat. Candidates create an account, complete identity verification, connect a Telegram identity, join mandatory recruitment communications, participate in a referral/verification workflow, become eligible for job application, and then attend a mandatory 7-day offline training in Jaipur.

**Important product-safety decision:** The original concept proposes exposing other applicants' Aadhaar/KYC data to referrers. This PRD does **not** implement raw Aadhaar sharing. Instead, the system uses privacy-preserving verification challenges/pseudonymous records. Aadhaar numbers must not become a public/domain identifier, and any Aadhaar authentication/e-KYC must be performed only through a legally permitted/authorized mechanism with informed consent and required security controls.

## 2. Vacancy Plan

| State | Posts |
|---|---:|
| Rajasthan | 5,000 |
| Uttar Pradesh | 4,500 |
| Gujarat | 5,500 |
| **Total** | **15,000** |

| Tier | Posts | Advertised monthly salary |
|---|---:|---:|
| Tier 1 | 1,000 | ₹2,10,000 |
| Tier 2 | 2,000 | ₹1,05,000 |
| Tier 3 | 13,000 | ₹21,000 |

No formal educational qualification is specified; selection is based on role requirements, training and hiring criteria.

## 3. Goals

- Secure signup/login.
- Referral attribution through referral links/codes.
- Consent-based identity/KYC workflow.
- Telegram account binding.
- Mandatory recruitment channel/group membership.
- Transparent referral progress.
- Fraud-resistant eligibility workflow.
- Batch management for offline Jaipur training.
- Admin-controlled hiring pipeline.
- Strong auditability and privacy.

## 4. Non-goals

- Do not expose applicants' Aadhaar numbers or Aadhaar cards to other applicants.
- Do not treat Telegram membership as proof of identity.
- Do not use Aadhaar number as an internal user ID.
- Do not claim a job is guaranteed merely because a candidate completes referrals.
- Do not collect more identity data than necessary.

## 5. Candidate Journey

1. Candidate opens referral link or direct signup.
2. Referral code is prefilled when supplied.
3. Candidate enters mobile number and password.
4. Candidate completes CAPTCHA and required consent.
5. Identity/KYC verification starts through the approved verification provider/process.
6. Candidate is issued a referral code.
7. Candidate opens Telegram bot.
8. Bot asks candidate to share Telegram contact.
9. Backend binds the Telegram user ID to the verified platform account.
10. Bot provides private channel/group join buttons.
11. Candidate sends join requests.
12. Bot/admin workflow verifies that the Telegram account is the bound account and approves the requests.
13. Candidate dashboard shows referral and verification requirements.
14. Candidate refers other people.
15. Referred people independently create accounts and complete KYC.
16. A referral counts only when the referred person's eligibility criteria are met.
17. For each referral count, the candidate completes an independent privacy-preserving verification challenge for a randomly selected eligible record. The challenge reveals no raw Aadhaar document.
18. Once the candidate reaches the configured threshold (default 200), job application becomes available.
19. Candidate selects state/tier/preferences subject to vacancy availability.
20. Eligible candidates are moved to the applicant pipeline.
21. Candidate receives batch/training information.
22. Candidate attends mandatory 7-day offline training in Jaipur.
23. Hiring decision and joining workflow are managed by recruitment admins.

## 6. Referral Rules

### Default
- 1 eligible referred candidate = 1 referral credit.
- Self-referral is prohibited.
- Duplicate accounts are prohibited.
- Referral credit is provisional until the referred candidate completes required verification.
- A rejected/failed KYC candidate does not count toward the referrer's threshold.
- A candidate is not punished solely because a referred candidate fails verification.
- Referral thresholds are configurable by admin.
- Default minimum: 200 verified referrals.

### Verification challenge
The platform should issue a random challenge record containing only the minimum information required for the candidate to perform the verification task. Prefer a one-time challenge token or masked identifier over Aadhaar documents.

## 7. Account States

`REGISTERED → IDENTITY_PENDING → IDENTITY_VERIFIED → TELEGRAM_PENDING → TELEGRAM_VERIFIED → GROUP_PENDING → ACTIVE → REFERRAL_IN_PROGRESS → APPLICATION_ELIGIBLE → APPLIED → TRAINING_SCHEDULED → TRAINING_ATTENDED → HIRED / NOT_SELECTED`

Additional exception states:
`SUSPENDED`, `REVIEW_REQUIRED`, `KYC_REJECTED`, `DUPLICATE_REVIEW`.

## 8. Core Screens

- Landing page
- Job/vacancy overview
- Signup
- Login
- Identity/KYC status
- Telegram connection
- Channel/group status
- Candidate dashboard
- Referral link/code
- Referral progress
- Verification challenges
- Application form
- Training schedule
- Application status
- Profile/security
- Privacy/consent
- Support

## 9. Admin Screens

- Dashboard
- Candidate search
- KYC review queue
- Fraud/duplicate queue
- Referral audit
- Telegram membership status
- Vacancy management
- State/tier allocation
- Application pipeline
- Training batches
- Attendance
- Hiring outcomes
- Audit logs
- System configuration

## 10. Acceptance Criteria

- Signup cannot create duplicate accounts under the same verified identity.
- Passwords are never stored in plaintext.
- Referral attribution is immutable after the defined attribution window.
- A referral credit is granted only after all configured eligibility checks pass.
- Telegram binding requires the bot flow and matching account context.
- Private chat/channel membership is verified server-side where technically supported.
- Candidate can always see why a referral did or did not count.
- Admin actions are audited.
- Sensitive identity values are encrypted/tokenized and access controlled.
- Raw Aadhaar documents are never exposed to referrers.

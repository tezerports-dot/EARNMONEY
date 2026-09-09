# UI/UX Design Document

## 1. Design Direction

The website should look like a legitimate professional recruitment portal rather than a promotional/referral website.

Style:
- Clean white/neutral foundation
- Strong typography
- Government/recruitment-style clarity without implying government ownership
- High contrast
- Mobile-first
- Clear status indicators
- Minimal animation
- No misleading urgency
- No exaggerated salary promises

## 2. Landing Page

Sections:
1. Header: logo, Jobs, How It Works, FAQ, Login
2. Vacancy summary
3. State cards
4. Tier cards
5. Eligibility overview
6. Recruitment process
7. 7-day Jaipur training requirement
8. Privacy/KYC explanation
9. CTA: Apply / Create Account

## 3. Signup

Step 1:
- Mobile number
- Password
- Confirm password
- CAPTCHA
- Referral code (prefilled if URL contains it)

Step 2:
- Identity verification
- Consent text
- Privacy notice

Step 3:
- Telegram connection

Step 4:
- Channel/group membership

Progress indicator:
`Account → Identity → Telegram → Groups → Referrals → Application`

## 4. Dashboard

Top:
- Candidate status
- Application eligibility
- Selected state/tier preference

Cards:
- Verified referrals: `X / 200`
- Verification challenges: `Y / X`
- Telegram: Connected
- Channel: Joined
- Group: Joined
- KYC: Verified
- Application: Locked/Available

Primary CTA should always be the next required action.

## 5. Referral Page

Display:
- Referral code
- Copy link
- Share buttons
- Number of referred candidates
- Number verified
- Number credited
- Reasons for non-credit

Do not display private information of referred users.

## 6. Verification Challenge

Show only minimum necessary challenge information.

Example:
> Verification task 34 of 120
> Candidate reference: `KYC-8F29`
> Enter the requested verification value.
> [Submit]

After submit:
- Passed
- Failed
- Needs review

Do not display full Aadhaar cards.

## 7. Job Application

Eligibility banner:
- KYC: ✓
- Telegram: ✓
- Referral requirement: 200/200
- Verification requirement: 200/200
- Training requirement: Pending

Application fields:
- Preferred state
- Preferred tier
- District preference
- Skills/work preference
- Availability
- Training availability

## 8. Training

Display:
- Batch number
- Jaipur venue
- Date
- Reporting time
- Documents to bring
- Attendance requirement
- Contact/support

## 9. Accessibility

- WCAG 2.2 AA target
- Keyboard navigability
- Screen-reader labels
- Minimum touch target size
- Error messages adjacent to fields
- Never rely on color alone
- Hindi + English localization ready

## 10. Critical UX Rules

- Never hide why a candidate is blocked.
- Never imply a candidate is hired before selection.
- Make privacy consequences explicit before identity verification.
- Make referral rules visible before referral activity.
- Provide an appeal/review path for failed verification.

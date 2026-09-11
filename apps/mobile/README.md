# BBAZAAR — candidate Android app

React Native (Expo) app for candidates of **BBAZAAR group of companies**. It is
a real native build, not a WebView wrapper, so AdMob works normally.

## Screens

| Screen | File | Access |
| --- | --- | --- |
| Home — vacancies and how to apply | `src/screens/HomeScreen.tsx` | Public |
| Sign up / log in | `src/screens/AuthScreen.tsx` | Public |
| Account + Telegram verification | `src/screens/AccountScreen.tsx` | Signed in |
| Referrals | `src/screens/ReferralScreen.tsx` | Verified |
| KYC training | `src/screens/TrainingScreen.tsx` | Verified |
| Apply for a job | `src/screens/ApplyScreen.tsx` | Both targets met |
| Selected candidates | `src/screens/SelectedScreen.tsx` | Both targets met |

Navigation is the horizontally scrollable row of card buttons in
`src/components/BrandHeader.tsx`, not a tab bar.

## Running it

```bash
npm install
npx expo start          # then press 'a' for an Android device/emulator
```

Point the app at your API by editing `expo.extra.apiBaseUrl` in `app.json`.
The default (`http://10.0.2.2:3001/api/v1`) is how an Android emulator reaches
a server running on your own machine.

## Building the APK

There is no Android SDK in this repo, so the APK is built by Expo's cloud
service:

```bash
npm install -g eas-cli
eas login
eas build:configure            # fills in expo.extra.eas.projectId
npm run build:apk              # installable .apk, for direct distribution
npm run build:aab              # .aab, for the Play Store
```

Building locally instead needs Android Studio plus `npx expo prebuild`.

## AdMob

`src/components/AdBanner.tsx` holds the banner. Two things to change before
release:

1. `PRODUCTION_BANNER_UNIT_ID` in that file — your real ad unit.
2. `androidAppId` in `app.json` — your real AdMob app id. Both currently hold
   Google's public test values.

Test ad units are selected automatically in development builds via `__DEV__`,
because serving live ads from a debug build is a common way to get an AdMob
account suspended.

## What this app deliberately does not do

**It makes no security decisions.** An APK can be unpacked and patched, so the
app never holds a secret and never decides what a user is entitled to:

- No API keys, tokens, or invite links are bundled. The selected-candidates
  group link is fetched from the server only after it confirms eligibility.
- The `locked` flag on a navigation card only dims it. Tapping through to a
  locked screen still produces a 403 from the server.
- Client-side form validation is for fast feedback only. Aadhaar checksum,
  password rules, duplicate detection, eligibility and fraud limits are all
  re-checked server-side, which is the copy that counts.
- Session cookies are held by the platform cookie jar, not in JavaScript. The
  only thing in SecureStore is the CSRF token, which is not a secret from the
  legitimate client.

Do not move any of these checks into the app to "save a request".

## For a design pass

`src/theme/tokens.ts` holds every colour, spacing step, radius and text style.
`src/components/ui.tsx` holds the presentational primitives — Card, Button,
Field, StatTile, ProgressBar, Badge, StepRow, Banner. Screens compose those and
own the data fetching. Restyling the app should mean editing those two files
plus the screens' local `StyleSheet` blocks, and nothing under `src/api/`.

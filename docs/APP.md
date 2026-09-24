# App navigation and design tokens

## Navigation

```text
/splash ─┬─ first launch ───────▶ /onboarding ──▶ /login
         ├─ no session ─────────▶ /login ⇄ /signup
         ├─ PENDING_VERIFICATION ▶ /verify ──▶ /verify/success
         └─ ACTIVE ─────────────▶ shell

shell (bottom navigation)
  /home        campaign, countdown, member counter, referral CTA
  /referrals   four-level table, share CTA
  /wallet      balances, recent entries, withdraw
  /profile     identity, verification status, settings, logout

secondary (pushed over the shell)
  /referrals/direct     level 1 list (paginated)
  /share                code, link, Share App + Referral
  /wallet/withdraw      review → confirm → submitting → result
  /wallet/bank          add or update bank details
  /wallet/history       withdrawals
  /how-it-works  /rules  /settings  /support  /terms  /privacy
  /celebration          shown once when the launch countdown ends

system states (replace the current screen until resolved)
  /offline   /maintenance   /upgrade
```

The router redirects on every change of session, account status or config. Verified screens are unreachable without a verified account, and the server enforces the same rule.

Bottom navigation has only the four main tabs (CLAUDE.md §18).

## Design tokens

Dark, premium, celebratory, and never casino-like. Tokens live in `mobile/lib/app/theme/`.

### Color

| Token | Value | Use |
|---|---|---|
| `ink` | `#0B0A14` | App background (deepest layer) |
| `night` | `#141226` | Raised background layer |
| `plum` | `#1F1A38` | Cards without glass |
| `glass` | white 7% + border white 12% | Glass cards |
| `gold` | `#E8C07A` | Primary actions, key figures |
| `goldBright` | `#F6DDA8` | Gradients, highlights |
| `violet` | `#7C5CFF` | Secondary accent, progress |
| `electric` | `#4C8DFF` | Links, info |
| `telegram` | `#2AABEE` | Telegram steps only |
| `success` | `#3DDC97` | Verified, paid |
| `warning` | `#F5B94C` | Pending, processing |
| `danger` | `#FF7A7A` | Failed, errors (soft, never alarm-red) |
| `textPrimary` | `#F5F3FF` | 15.9:1 on `ink` |
| `textSecondary` | `#BEB8D6` | 9.6:1 on `ink` |
| `textMuted` | `#8E88AA` | 5.5:1 on `ink`, captions only |

Status is never shown by color alone: every status chip has an icon and a word.

### Type

| Token | Font | Size / line height |
|---|---|---|
| `display` | Playfair Display, bold | 40 / 46 |
| `headline` | Playfair Display, semibold | 28 / 34 |
| `title` | Manrope, bold | 20 / 26 |
| `body` | Manrope, medium | 16 / 24 |
| `bodySmall` | Manrope, medium | 14 / 20 |
| `label` | Manrope, bold | 14 / 18 |
| `caption` | Manrope, semibold | 12 / 16 (smallest size used) |
| `figure` | Manrope, extra bold, tabular figures | 32 / 38 (amounts and counters) |

Fonts are bundled in the APK (SIL Open Font License). All text follows the phone's text-size setting.

### Spacing, radius, motion

- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 56. Screen side padding is 20.
- Radius: cards 24, buttons 16, inputs 16, chips 12, sheets 28.
- Minimum tap target: 48 × 48.
- Motion: 150 ms (taps), 250 ms (transitions), 400 ms (card entrance), 1,200 ms (counters). When the phone asks for reduced motion, durations drop to zero and particles are hidden.
- At most two looping animations on a screen.

### Money and numbers

- Amounts are integer paise from the server, and formatting never uses floating point.
- Indian grouping: `₹1,15,000`, `1,15,77,956`. Whole rupees show no decimals, and anything else shows two.

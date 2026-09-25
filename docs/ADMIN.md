# Admin guide

The admin panel is at `https://your-domain/admin`. Sign in with your username, password and the 6-digit code from your authenticator app. Sessions last 8 hours. Every change, payout file download and flag decision is written to the audit log with the admin's name and IP address.

Admins are created on the server (see [SETUP.md](SETUP.md), step 5). There's no sign-up page and no password reset by email: another admin with server access creates a new account.

## First-time checklist

Do these in order before sharing the app.

1. **Settings.** Enter the registered legal name, address and support email. The app's terms and privacy pages use them. Set the APK download URL ([RELEASE.md](RELEASE.md)) and the minimum app version.
2. **Bots.** Add one **watcher** bot and at least one **verifier** bot, using tokens from @BotFather. Add more verifiers as sign-ups grow. Each verifier's weight sets its share of new verifications.
3. **Channels.** Add each channel users must join. Make the watcher bot an admin of each channel with the "Invite users" right, so it can see join requests. Leave the invite link empty to let the watcher create a join-request link.
4. **Campaign.** Check the dates (brand reveal 21 December, launch and payout 31 December 2026), the level 1 reward (₹200), the minimum withdrawal and the member capacity.
5. **Fund the promotional pool** (Campaign page). Record only money that is really set aside. Rewards are paid from the pool; when it's empty, new rewards stop and the app says rewards are closed.
6. **Try it yourself** with a real phone: sign up, verify through Telegram, refer a second phone, and check the reward appears as pending.

## Pages

### Dashboard

At a glance:

- campaign status, and whether sign-ups and rewards are open;
- verified members against capacity;
- accounts waiting for verification and suspended accounts;
- promotional pool left, funded and paid out;
- withdrawals by status and open fraud flags;
- the job queue, with the age of its oldest ready job. If that keeps growing, the worker is behind.

### Campaign

- **Dates** (in IST): start, end, brand reveal, launch and payout date. The app's countdown and the payout date come from here.
- **Brand name.** The app shows it only from the brand reveal time.
- **Level 1 reward:** ₹ per verified direct referral. A change applies to new rewards only; rewards already credited keep their amount. Levels 2–4 always pay ₹0, and there's deliberately no setting for them.
- **Minimum withdrawal** and **capacity** (members).
- **Pause** stops new rewards. **Sign-ups open** closes new sign-ups, which also close by themselves at capacity.
- **Show promotional allocation.** When on, the app shows the total actually recorded in the pool, never a typed-in figure.
- **Fund the pool.** Each recording is a ledger entry and can't be edited. Submitting the same form twice records it once.

There is no setting for the member count. It is always the real number of verified users.

### Settings

- company name, legal name, address, support email and URL, terms and privacy URLs;
- minimum app version and APK download URL;
- **maintenance mode:** a message and an optional end time. The app shows it instead of its screens, while admin pages keep working;
- **announcement banner:** a short message on the app's home screen;
- **ads:** banner, interstitial and rewarded on or off, and the minimum seconds between interstitials. Ads never appear on sign-up, verification, wallet or withdrawal screens;
- **verification rules:** how long a verification link lasts, how many wrong phone numbers a link allows, and whether a pending channel join request counts as joining.

### Bots and Channels

Add, disable or re-enable bots and channels. Bot tokens are stored encrypted and never shown again. The server registers each bot's webhook with a secret only it knows. A bot that keeps failing is taken out of rotation automatically, and users waiting on it get a healthy bot the next time they open verification.

Join requests are **never approved automatically**. Approve or decline them in Telegram as you wish. By default a sent request is enough to verify; switch off "pending requests count" in Settings to require your approval first.

### Users

Search by public id or phone number. A user's page shows their status, referrer, direct referrals, balances, bank details (masked) and risk flags. You can **suspend** an account, which signs it out everywhere, blocks the app and holds its withdrawals out of payout batches, or **unsuspend** it. You can't change who referred someone: referrers are fixed at sign-up.

### Withdrawals: payout day

Withdrawal requests open on the payout date (31 December 2026). Each request moves the amount from the user's available balance into a clearing account, so nobody can request the same money twice.

1. **Withdrawals → Requested → Create a payout batch.** The oldest requests (up to 1,000) move to **Processing**. Requests from users with an **open risk flag** or a **suspended account are held back**; they stay Requested until the flag is resolved or the suspension lifted.
2. **Download the batch file** (CSV: withdrawal id, account holder, full account number, IFSC, amount). The file holds full bank numbers: every download is audit-logged. Keep it off shared drives and delete it after use.
3. Pay the rows through the bank.
4. For each row, record **Paid** with the bank reference (UTR), or **Failed** with a reason. A failed withdrawal returns the money to the user's available balance, and they can request again.

Only these steps change a withdrawal's status. The app can't mark anything paid.

### Flags

Fraud signals, for a person to judge:

- **SHARED_BANK_ACCOUNT:** several accounts saved the same bank account;
- **REFERRAL_BURST:** 30 or more of someone's friends verified within an hour.

A flag doesn't take anything away and isn't shown to the user. It only holds their withdrawals out of payout batches until an admin looks. Resolve it to release them, or suspend the account if it's abuse.

### Audit log and Ledger

- **Audit log:** every admin action and important system event, newest first. It can't be edited.
- **Ledger:** reconciliation. All balances must sum to zero, and every account's balance must equal the sum of its entries. The page shows any account that doesn't match. There should never be one; if there is, stop payouts and investigate.

## Things the panel deliberately can't do

- set or inflate the member count;
- pay levels 2–4, or set a reward for them;
- change or remove who referred someone;
- edit or delete ledger entries or audit records;
- mark a withdrawal paid outside a batch, or without a bank reference.

These rules are enforced by the server and, for money, by the database itself (see [DATABASE.md](DATABASE.md)).

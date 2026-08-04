# Management guide

Day-to-day running, once [SETUP.md](SETUP.md) is done. Written for the person
operating the business, not maintaining the code.

---

## The monthly payout cycle

This is the one routine that matters. Months run **1st 00:00 IST to the last
day 23:59 IST**.

### During the month

Nothing to do. Members earn automatically. You can watch
**Admin → Dashboard** for the running total of what you will owe.

### On the 1st of the next month

You get a Telegram message from the bots: *"July closed — 412 referrers, 3,890
active members, ₹19,450 payable."* That is your bill for the month that just
ended.

### Paying out — five steps

1. **Admin → Withdrawals**, pick last month in the dropdown.
2. Review the pending requests. Click **Approve** on the good ones, **Reject**
   on any that look wrong (a rejection can carry a reason the member sees).
3. **Admin → Export**, pick the same month, click **Download .xlsx** (or CSV
   if your bank prefers it).
4. Upload that file to your bank's bulk-transfer page and make the transfers.
5. Back in **Withdrawals**, click **Mark paid** on each row you actually paid.
   Each member gets a Telegram message confirming the transfer.

**Before you upload, check the red banner on the Export page.** If it says
rows were skipped, those members requested a payout but never submitted bank
details. Chase them from **Admin → Bank** and re-export.

### What is in the file

Five columns, exactly what a bank bulk-upload expects: Full Name, Account
Number, IFSC, UPI ID, Amount (INR). Account numbers are stored as text in the
`.xlsx`, so a 16-digit number keeps its leading zeros instead of turning into
`1.23457E+15`.

---

## Sending an announcement

1. Open your **broadcast bot** in Telegram (only accounts in `ADMIN_IDS` can
   use it).
2. Send it anything — text, a photo, a video, a document, even a forwarded
   post.
3. It asks *"Send this to N managed chats?"* — tap the button.

It copies your message into every group and channel once each, even when
different bots cover different chats. It reports how many succeeded and names
any that failed.

**Commands**

| Command | Does |
|---|---|
| `/targets` | Lists every chat it will post to |
| `/say <text>` | Sends plain text with no confirmation step |
| `/poll Question \| Option A \| Option B` | Posts a poll to every group |
| `/confirm off` | Stop asking for confirmation (`/confirm on` to restore) |

**Use `/poll` rather than posting polls by hand.** Telegram only tells a bot
about votes on polls the *bot itself* created. A poll you post from your own
account produces no signal at all, so those votes cannot count as activity.

---

## Collecting bank details

The collector bot handles this automatically: once a day it posts a reminder
in every chat and sends a direct message to members who have not submitted
theirs yet.

- Run it early: **Admin → Bank → Run the reminder sweep now**.
- Change the wording: **Admin → Settings → `daily_prompt_text`**.
- Change the hour: `DAILY_PROMPT_HOUR` in `/opt/referral/.env` (restart after).
- See who still owes: **Admin → Bank**, "Still missing" table.

The direct-message sweep is capped (`daily_prompt_dm_limit`, default 2000/day)
because Telegram rate-limits outbound messages. It always chases the newest
members first.

**Bank details can only be submitted once.** That is deliberate: it stops
someone who takes over a member's Telegram account from redirecting the
payout. If a member genuinely mistyped their account number, you must correct
it yourself — see "Fixing a member's bank details" below.

---

## Moderation

The moderation bot works on its own once it is an admin with Group Privacy
off. It deletes forbidden words, blocks links from unverified members, and
escalates warnings to a mute and then a ban.

**In-chat commands** (for anyone who is an admin of that chat):

| Command | Does |
|---|---|
| `/ban` (reply to a message) | Bans from **every** managed chat |
| `/unban UID-A1B2C3` | Lifts the ban everywhere and clears warnings |
| `/mute 30` (reply) | Mutes for 30 minutes in that chat |
| `/unmute` (reply) | Lifts a mute |
| `/warn` (reply) | Adds a warning |
| `/unwarn` (reply) | Clears warnings in that chat |
| `/whois` (reply) | Shows their ID, status and eligibility |

**Tunable at Admin → Settings**

| Setting | Meaning | Default |
|---|---|---|
| `moderation_enabled` | Master switch (`1`/`0`) | `1` |
| `banned_words` | Comma-separated list | empty |
| `block_links_from_unverified` | Delete links from unverified members | `1` |
| `flood_limit` / `flood_window_seconds` | Messages allowed in that window | 6 / 8 |
| `warn_mute_at` / `warn_ban_at` | Warnings before a mute / a ban | 3 / 5 |
| `mute_minutes` | Length of an automatic mute | 60 |

Changes apply immediately — no restart.

---

## Adding capacity

One group can hold 200,000 members; a channel is unlimited. When a group fills
up, add another **pair**.

1. Create a new group and a new channel in Telegram.
2. Add all four bots as administrators with the "invite users" right.
3. **Admin → Chats & pairs → Create a pair**, pick the new group and channel.
4. Click **Make default** on the new pair.

New members go to the new pair. Existing members stay where they are, and
their referrals follow *them*, so friends stay together. Set a **Capacity** on
a pair to have it stop accepting people automatically once it is full.

---

## Common jobs

### Fixing a member's bank details

The bot has no update path on purpose. To correct one:

```bash
sudo sqlite3 /opt/referral/data/referral.db \
  "DELETE FROM bank_details WHERE user_id = (SELECT id FROM users WHERE uid = 'UID-A1B2C3');"
```

Then ask them to send `/bank` again. Verify who you are talking to first —
this is exactly the path an account thief would ask you to take.

### Banning someone permanently

**Admin → Users**, search their ID, open them, click **Ban everywhere**. They
are removed from every chat, cannot rejoin, and stop counting for whoever
referred them.

### Someone has two accounts

The phone-number check catches this at signup. If you spot one another way,
open the newer account and click **Mark as duplicate** — it is banned and
detached from its referrer immediately.

### Changing the payout rates

**Admin → Settings**, edit `payout_level1` and `payout_level2`, save. Applies
immediately, including to the month in progress. Set level 2 to `0` to turn
off indirect earnings entirely.

### Changing the welcome message

**Admin → Settings → `welcome_text`**. Basic HTML works: `<b>bold</b>`,
`<i>italic</i>`, `<code>code</code>`.

---

## Backups

**Do this before you have real members.** SQLite is one file; backing it up is
one command that is safe to run while the service is up.

Set up a nightly backup:

```bash
sudo mkdir -p /opt/referral/backups
sudo tee /opt/referral/backup.sh > /dev/null <<'EOF'
#!/bin/bash
STAMP=$(date +%Y%m%d)
sqlite3 /opt/referral/data/referral.db ".backup /opt/referral/backups/referral-$STAMP.db"
gzip -f /opt/referral/backups/referral-$STAMP.db
find /opt/referral/backups -name '*.db.gz' -mtime +30 -delete
EOF
sudo chmod +x /opt/referral/backup.sh
echo "0 3 * * * root /opt/referral/backup.sh" | sudo tee /etc/cron.d/referral-backup
```

That keeps 30 days of nightly backups on the server. **Copy them off the
server too** — a backup on the same machine does not survive losing the
machine. Download the latest one to your own computer:

```bash
scp -i ~/Downloads/your-key.key ubuntu@YOUR_IP:/opt/referral/backups/*.gz .
```

### Restoring

```bash
sudo systemctl stop referral
sudo gunzip -c /opt/referral/backups/referral-20260804.db.gz \
  | sudo tee /opt/referral/data/referral.db > /dev/null
sudo chown referral:referral /opt/referral/data/referral.db
sudo systemctl start referral
```

---

## Updating to a newer version

```bash
cd ~/EARNMONEY
git pull
sudo cp -r app deploy requirements.txt /opt/referral/
sudo /opt/referral/venv/bin/pip install -r /opt/referral/requirements.txt
sudo chown -R referral:referral /opt/referral
sudo systemctl restart referral
sudo journalctl -u referral -n 30
```

Take a backup first. Your `.env`, your database and everything in the admin
panel are left alone.

---

## Monitoring

| What | How |
|---|---|
| Is it up? | `https://yourdomain.com/healthz` returns `{"status":"ok"}` |
| Live log | `sudo journalctl -u referral -f` |
| Errors only | `sudo journalctl -u referral -p err -n 50` |
| Memory | `free -h` — expect the app to use 200–400 MB |
| Disk | `df -h` — expect roughly 200 bytes per member |
| Audit trail | **Admin → Events** (verifications, bans, payouts, logins) |

The dashboard flags any bot missing admin rights in one of its chats. Check it
after adding a new group or channel.

---

## Things that will surprise you

**Members cannot be added to a group by a bot.** Telegram does not allow it,
at all. Each member gets a personal invite link and taps it once; the bots
approve them instantly. That is as close to automatic as the platform permits.

**You cannot see who "read" a channel post.** Telegram sends bots no such
event. Activity is only: a button tap, a command, a group message, a vote on a
bot-created poll, or a direct message to a bot.

**Extra activity never pays extra.** One interaction in the month is the whole
requirement. Somebody who taps a hundred buttons is worth exactly what
somebody who taps one is worth.

**Activity history is two months deep.** The current month and the previous
one — enough to run and audit a payout. Older months read as "not active"
because the data is genuinely gone; the withdrawals table is the permanent
record of what was paid, and it is never pruned.

**Only run one copy.** Telegram allows one connection per bot token. Never
start a second server with the same tokens, or both will fail with a conflict
error.

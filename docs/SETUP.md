# Setup guide

**For someone who has never written code.** Follow it top to bottom. Every
command is meant to be copied and pasted exactly. After each step there is a
**Check** — if the check does not match, stop there and fix it before going on.

Total time: about 60–90 minutes, most of it waiting.

**What you need before you start**

- A credit or debit card (Oracle asks for one to verify identity — the Always
  Free resources are not charged).
- A domain name, e.g. `myreferral.com`. About ₹800/year from any registrar.
- The Telegram app, on your phone or desktop.

---

## Part 1 — Get a free server from Oracle

### 1.1 Create the account

1. Go to <https://signup.oracle.com/>.
2. Choose your country and fill in your details.
3. For **Home Region**, choose **India South (Hyderabad)** or **India West
   (Mumbai)**. Pick carefully — this cannot be changed later.
4. Verify your card. You will see a temporary hold of about ₹85; it is
   refunded.
5. When it asks, stay on the **Always Free** account.

### 1.2 Create the server

1. Sign in to <https://cloud.oracle.com/>.
2. In the top-left menu (☰) choose **Compute → Instances**.
3. Click **Create instance**.
4. **Name**: `referral-server`
5. Under **Image and shape**, click **Edit**:
   - Click **Change image**, pick **Canonical Ubuntu**, choose version
     **24.04**, click **Select image**.
   - Click **Change shape**, choose the **Ampere** tab, pick
     **VM.Standard.A1.Flex**.
   - Set **OCPUs** to `2` and **Memory** to `12` GB. Click **Select shape**.
6. Under **Add SSH keys**, choose **Generate a key pair for me** and click
   **Save private key**. A file downloads — usually to your Downloads folder.
   **Keep this file. Without it you cannot get into your server.**
7. Click **Create**. Wait about two minutes until the box turns green and says
   **RUNNING**.
8. Copy the **Public IP address** shown on the page. It looks like
   `152.67.xxx.xxx`. Write it down.

> **"Out of capacity" error?** Oracle's free Ampere machines are popular. Try
> a different Availability Domain in the dropdown, or try again in a few
> hours. It is not something you did wrong.

### 1.3 Open the network ports

Oracle blocks web traffic by default. This step is easy to forget and is the
single most common reason the site does not load later.

1. On your instance page, under **Primary VNIC**, click the **Subnet** link.
2. Click the **Security List** (usually "Default Security List for ...").
3. Click **Add Ingress Rules** and add these two, one at a time:

| Field | First rule | Second rule |
|---|---|---|
| Source CIDR | `0.0.0.0/0` | `0.0.0.0/0` |
| IP Protocol | TCP | TCP |
| Destination Port Range | `80` | `443` |

4. Click **Add Ingress Rules** to save.

**Check:** the Security List now shows rules for ports 22, 80 and 443.

---

## Part 2 — Point your domain at the server

1. Sign in wherever you bought your domain (GoDaddy, Namecheap, Hostinger…).
2. Find **DNS** / **Manage DNS** / **DNS Records**.
3. Add a record:
   - **Type**: `A`
   - **Name** / **Host**: `@`
   - **Value** / **Points to**: your server's public IP from step 1.2
   - **TTL**: leave as is
4. Save.

**Check:** wait 10 minutes, then on your own computer open a terminal and run
`ping myreferral.com` (use your domain). It should reply with your server's
IP. If it still shows the old address, wait longer — DNS can take up to an
hour.

---

## Part 3 — Connect to the server

### On Windows

1. Press `Win + R`, type `cmd`, press Enter.
2. Type this, replacing the path with where your key file downloaded and the
   IP with yours:

```
ssh -i C:\Users\YourName\Downloads\ssh-key-2026-08-04.key ubuntu@152.67.xxx.xxx
```

If it complains the key is "unprotected", run this first, then try again:

```
icacls C:\Users\YourName\Downloads\ssh-key-2026-08-04.key /inheritance:r /grant:r "%USERNAME%":R
```

### On Mac or Linux

1. Open **Terminal**.
2. Lock down the key file, then connect:

```bash
chmod 600 ~/Downloads/ssh-key-2026-08-04.key
ssh -i ~/Downloads/ssh-key-2026-08-04.key ubuntu@152.67.xxx.xxx
```

The first time it asks "Are you sure you want to continue connecting?" — type
`yes` and press Enter.

**Check:** your prompt now ends with something like `ubuntu@referral-server:~$`.
You are on the server. Everything from here is typed into this window.

---

## Part 4 — Install the software

Copy and paste these three lines, one at a time, pressing Enter after each and
waiting for it to finish:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/tezerports-dot/EARNMONEY.git
cd EARNMONEY && sudo bash deploy/install.sh
```

The last one takes 3–5 minutes and prints a lot of text. At the end it prints
a block starting with **"Done. Next:"** which includes a line like:

```
Your generated admin token is:
  8f3a9c2e1b7d4a5f6e8c9d0a1b2c3d4e5f6a7b8c9d0e1f2a
```

**Copy that long string into a notes app now.** It is the password to your
control panel. It is shown once here; you can always read it again later with
`sudo grep ADMIN_TOKEN /opt/referral/.env`.

**Check:** you see "Done. Next:" with no red error text above it.

---

## Part 5 — Create your Telegram bots

Do this part on your phone or Telegram desktop, not on the server.

### 5.1 Find your own Telegram ID

1. In Telegram, search for **@userinfobot** and open it.
2. Press **Start**.
3. It replies with `Id: 123456789`. **Write that number down.**

### 5.2 Create four bots

1. In Telegram, search for **@BotFather** and open it.
2. Send `/newbot`.
3. It asks for a name — type anything, e.g. `My Referral Bot`.
4. It asks for a username — must end in `bot`, e.g. `myreferral_main_bot`.
5. It replies with a token that looks like
   `7891234567:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`. **Copy it to your notes.**

Repeat `/newbot` three more times so you have four bots. Suggested names:

| Purpose | Suggested username | What it does |
|---|---|---|
| Main | `myreferral_main_bot` | Signs people up, gives out referral links, handles payouts |
| Moderation | `myreferral_mod_bot` | Keeps the groups clean, enforces bans |
| Collector | `myreferral_bank_bot` | Asks members for bank details daily |
| Broadcast | `myreferral_news_bot` | You message it once, it posts everywhere |

### 5.3 Let the moderation bot read messages

By default Telegram hides group messages from bots. The moderation bot needs
to see them.

1. In BotFather, send `/mybots`.
2. Choose your **moderation** bot.
3. Tap **Bot Settings → Group Privacy → Turn off**.

**Check:** it says "Privacy mode is disabled for ...".

---

## Part 6 — Tell the server about your bots

Back in the server window:

```bash
sudo nano /opt/referral/.env
```

A text editor opens. Use the arrow keys — the mouse does not work here.

Change these lines (leave the rest alone):

- `ADMIN_IDS=` → put your Telegram ID from step 5.1, e.g. `ADMIN_IDS=123456789`
- `PUBLIC_BASE_URL=` → your domain with `https://`, e.g.
  `PUBLIC_BASE_URL=https://myreferral.com`
- `BOT_TOKENS=` → all four tokens, in this exact shape, all on **one line**,
  separated by commas with no spaces:

```
BOT_TOKENS=main:7891234567:AAHxxx,moderation:7891234568:AAHyyy,collector:7891234569:AAHzzz,broadcast:7891234570:AAHwww
```

To save: press `Ctrl+O`, then Enter, then `Ctrl+X`.

Now tell nginx your domain:

```bash
sudo sed -i 's/referral.example.com/myreferral.com/' /etc/nginx/sites-available/referral
sudo nginx -t && sudo systemctl reload nginx
```

(Replace `myreferral.com` with your real domain.)

**Check:** `nginx -t` says `syntax is ok` and `test is successful`.

---

## Part 7 — Start it

```bash
sudo systemctl start referral
sudo systemctl status referral
```

**Check:** you see `Active: active (running)` in green. Press `q` to exit that
view.

To watch what it is doing:

```bash
sudo journalctl -u referral -f
```

You should see lines like `started bot 1 (@myreferral_main_bot) as main`.
Press `Ctrl+C` to stop watching.

**Check:** open `http://myreferral.com` in a browser. You should see the
member lookup page.

> **Nothing loads?** Ninety percent of the time it is Part 1.3 — go back and
> confirm ports 80 and 443 are open in the Oracle Security List.

---

## Part 8 — Turn on HTTPS

Free, and takes a minute. Do not skip it: without it your admin password
travels in the clear.

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d myreferral.com
```

- Enter your email when asked.
- Type `Y` to agree to the terms.
- Choose `2` (redirect all traffic to HTTPS) if it offers.

**Check:** `https://myreferral.com` loads with a padlock in the address bar.

---

## Part 9 — Create your groups and channels

In Telegram:

1. Create a **group**. Name it whatever you like.
2. Create a **channel**. Name it whatever you like.
3. Add **all four bots** to the group:
   - Open the group → tap its name → **Administrators** → **Add Admin**
   - Search each bot, select it, and make sure these switches are **on**:
     **Delete messages**, **Ban users**, **Invite users via link**
   - Tap the ✓ to save. Do this for each of the four bots.
4. Do exactly the same for the **channel**.

**Check:** each bot appears in the Administrators list of both the group and
the channel.

---

## Part 10 — Finish in the control panel

1. Open `https://myreferral.com/admin` in a browser.
2. Paste the admin token from Part 4. Click **Log in**.
3. Go to **Bots**. All four should be listed as **running** with green
   badges. If one shows an error, the token was mistyped — remove it and add
   it again with the correct token.
4. Go to **Chats & pairs**. Your group and channel should already be listed —
   they register themselves when a bot is made an administrator. If not, add
   them by ID.
5. Under **Create a pair**, pick your group and your channel and click
   **Create pair**.
6. On the pair that appears, click **Make default** and **Make primary**.

**Check:** the pair shows both a `default` and a `primary` badge.

---

## Part 11 — Test it yourself

1. Open your main bot in Telegram and press **Start**.
2. Tap the single button. It should share your contact and immediately reply
   with your ID (`UID-XXXXXX`), your referral link, and two buttons to join
   the group and the channel.
3. Tap both buttons. You should be let in automatically.
4. Send `/status` to the bot. It should say you are in your group, in your
   channel, and have interacted this month.
5. Open `https://myreferral.com` and search for your `UID-XXXXXX`.

**Check:** your public page loads and shows you as verified and active.

Now send your referral link to a friend and have them do the same. After they
finish, your `/earnings` should show ₹5 for them.

---

## You are live

Your system is running. What to do next:

- **Read [MANAGEMENT.md](MANAGEMENT.md)** — how to broadcast, run the monthly
  payout, and handle problems.
- **Set your payout rates** at **Admin → Settings** if ₹5 + ₹5 is not what you
  want.
- **Set up backups** — see MANAGEMENT.md. Do this before you have real
  members, not after.

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| Website does not load at all | Ports 80/443 not open in the Oracle Security List (Part 1.3). |
| "502 Bad Gateway" | The app is not running: `sudo systemctl restart referral`, then `sudo journalctl -u referral -n 50`. |
| Bots show as stopped | A token is wrong. Compare against BotFather, remove the bot in the panel and add it again. |
| Bot does not reply in Telegram | Check it is running in the panel; check `sudo journalctl -u referral -f` while you message it. |
| "Bot is not an administrator" warning | Re-add the bot as an admin **with the "invite users" right**. |
| Moderation bot ignores group messages | Group Privacy is still on — see step 5.3. |
| New members get no join links | No pair is configured, or it is not marked default (Part 10, steps 5–6). |
| Lost the admin password | `sudo grep ADMIN_TOKEN /opt/referral/.env` |
| Locked out after wrong passwords | Wait 5 minutes; the lockout clears itself. |

**Useful commands**

```bash
sudo systemctl restart referral          # restart everything
sudo systemctl stop referral             # stop everything
sudo journalctl -u referral -f           # watch the live log
sudo journalctl -u referral -n 100       # last 100 log lines
sudo nano /opt/referral/.env             # edit settings (restart after)
df -h                                    # check disk space
free -h                                  # check memory
```

After editing `.env` you must run `sudo systemctl restart referral` for the
change to take effect. Settings changed in the **admin panel** apply
immediately and need no restart.

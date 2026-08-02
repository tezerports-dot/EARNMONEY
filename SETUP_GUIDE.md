# Setup Guide — No Coding Experience Needed

This walks you through launching your Telegram Referral Platform from zero, one click at a time.
Total time: about 45–90 minutes the first time.

---

## What you'll need before starting

- [ ] A computer with internet access
- [ ] A Telegram account
- [ ] A credit/debit card (for Oracle Cloud identity verification only — the server itself is free, see Part 3)
- [ ] About an hour of uninterrupted time

---

## Part 1 — Create your Telegram bot

1. Open Telegram (app or web.telegram.org).
2. In the search bar, type **BotFather** and open the chat with the blue checkmark (official).
3. Tap **Start**.
4. Send the message: `/newbot`
5. BotFather asks for a **name** — this is the display name (e.g. `Referral Rewards`). Type it and send.
6. BotFather asks for a **username** — this must end in `bot` (e.g. `ReferralRewardsBot`). Type it and send.
7. BotFather replies with a message containing a long string of letters and numbers after "Use this token to access the HTTP API:" — this is your **Bot Token**.
   **Copy this token somewhere safe (like a Notes app). You'll paste it in Part 4.**
8. Still in BotFather, send `/setprivacy`, pick your bot from the list, and choose **Disable**. This lets your bot see when people join/leave your channel and group later.

---

## Part 2 — Create your Telegram channel and group

You need one **channel** and one **group** to start (you can add more later from the admin panel).

### Create the channel
1. In Telegram, tap the pencil/compose icon → **New Channel**.
2. Give it a name (e.g. "Referral Rewards Channel"), tap **Next**, then **Create** (make it Public or Private — Private is recommended).
3. Once created, tap the channel name at the top → **Invite Links** → copy the invite link. **Save this link.**
4. Tap the channel name → **Administrators** → **Add Admin** → search for your bot's username → add it → make sure "Invite Users via Link" and viewing member list permissions are turned on → confirm.

### Create the group
1. Tap the pencil/compose icon → **New Group**.
2. Add at least one contact (you can remove them later), name the group (e.g. "Referral Rewards Group"), tap **Create**.
3. Tap the group name → **Add Members** → search for your bot's username → add it.
4. Tap the group name → **Administrators** → **Add Admin** → select your bot → confirm.
5. Tap the group name → **Invite Links** (or **Invite to Group via Link**) → copy the invite link. **Save this link.**

### Get the numeric Chat IDs (needed in Part 6)
1. Forward any message from your channel to the bot **@userinfobot** (search for it, tap Start, then forward a message from your channel into that chat). It will reply with a **Chat ID** — usually a negative number starting like `-100...`. **Save this number** and label it "Channel Chat ID."
2. Repeat by forwarding a message from your group to **@userinfobot** to get the **Group Chat ID**. **Save this number** too.

---

## Part 3 — Create your free Oracle Cloud server

We'll use **Oracle Cloud's Always Free tier** (Ampere/ARM), which gives you a genuinely
permanent free server (2 OCPUs / 12 GB RAM) — no trial expiry, no monthly bill as long as you
stay within the free limits.

### Create your Oracle Cloud account
1. Go to **oracle.com/cloud/free** and click **Start for free**.
2. Fill in your email, then check your inbox and verify it.
3. Complete the signup form: name, address, and a **credit/debit card** (required for identity
   verification only — you will not be charged unless you later explicitly upgrade and exceed the
   free limits). A phone number for SMS verification is also required.
4. Choose your **Home Region** carefully — you cannot change this later. Regions closer to India
   (e.g. `ap-mumbai-1`, `ap-hyderabad-1`) usually make sense, but if you hit the capacity error
   described further down this section, a less busy region (e.g. `uk-london-1`, `eu-frankfurt-1`)
   may succeed instead.
5. Wait for the "Account provisioning" step to finish (a few minutes to a few hours).

### Create the server (instance)
1. Once logged into the Oracle Cloud Console, open the menu (☰ top-left) → **Compute** →
   **Instances** → **Create Instance**.
2. Give it a name, e.g. `referral-platform`.
3. Under **Image and shape**, click **Edit**:
   - **Image:** select **Canonical Ubuntu**, version **24.04**
   - **Shape:** click **Change shape** → select **Ampere** → **VM.Standard.A1.Flex** → set
     **2 OCPUs** and **12 GB memory** (the free-tier maximum)
4. Under **Add SSH keys**, choose **Save private key** — click it and save the downloaded `.key`
   file somewhere safe on your computer (e.g. Desktop). This replaces a password — you'll use this
   file to log in.
5. Leave everything else as default, scroll down, and click **Create**.
6. Wait until the instance status shows a green **Running** dot, then copy its **Public IP
   address** shown on the instance's details page.

### Open the web ports (Oracle blocks these by default)
1. Still on the instance's details page, click the link under **Primary VNIC** → **Subnet** (it
   opens a new page).
2. Click the **Default Security List** link.
3. Click **Add Ingress Rules**, and add two rules (repeat for each):
   - Source CIDR: `0.0.0.0/0`, IP Protocol: `TCP`, Destination Port Range: `80`
   - Source CIDR: `0.0.0.0/0`, IP Protocol: `TCP`, Destination Port Range: `443`
4. Click **Add Ingress Rules** to save.

### Connect to your server
- **On Mac/Linux:** open **Terminal**, then run (replace the path and IP with your own):
  ```
  chmod 600 ~/Desktop/ssh-key-*.key
  ssh -i ~/Desktop/ssh-key-*.key ubuntu@YOUR_SERVER_IP
  ```
- **On Windows:** download and open **PuTTY** and **PuTTYgen**. In PuTTYgen, click **Load**,
  select your downloaded `.key` file, then **Save private key** as a `.ppk` file. In PuTTY, enter
  your server's IP, go to **Connection → SSH → Auth → Credentials**, browse to your `.ppk` file,
  then click **Open** and log in as `ubuntu`.

You should now see a prompt like `ubuntu@referral-platform:~$`. This is where you'll type the
commands below. Note the username is **`ubuntu`**, not `root` — every command below that needs
admin rights uses `sudo` for this reason.

> **If instance creation fails with "Out of host capacity":** this means Oracle's free Ampere
> capacity is temporarily full in that region. Either try again in a few hours, try a different
> availability domain (shown as a dropdown during creation), or switch your account to
> "Pay As You Go" billing in Account Management (still $0 unless you exceed free limits) — this
> gives access to a larger capacity pool and usually resolves it immediately.
---

## Part 4 — Install Docker on your server

Copy and paste each line below into your server's terminal, pressing Enter after each one, and waiting for it to finish before pasting the next:

```
curl -fsSL https://get.docker.com | sudo sh
```

```
sudo apt-get install -y docker-compose-plugin unzip
```

```
sudo usermod -aG docker ubuntu && newgrp docker
```

The last command lets you run `docker` commands without typing `sudo` every time for the rest of
this guide.

Oracle's Ubuntu image also has its own firewall in front of the ports we opened in Part 3 — open
them there too:
```
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```
(If that last command says "command not found," run `sudo apt-get install -y iptables-persistent`
first, then try it again — it'll ask two yes/no questions, answer **Yes** to both.)

---

## Part 5 — Upload the project files

1. Download the `telegram-referral-platform.zip` file provided to you onto your own computer.
2. Upload it to your server. The easiest way:
   - **Windows:** use **WinSCP** (free) — connect using your server's IP, username `ubuntu`, and
     your `.ppk` private key (same one from Part 3), then drag the zip file onto the server.
   - **Mac/Linux:** open a new Terminal tab (keep the SSH one open) and run, from the folder where
     you downloaded the zip (adjust the key path to match yours):
     ```
     scp -i ~/Desktop/ssh-key-*.key telegram-referral-platform.zip ubuntu@YOUR_SERVER_IP:~/
     ```
3. Back in your SSH terminal window, run:
   ```
   cd ~
   unzip telegram-referral-platform.zip
   cd telegram-referral-platform
   ```

---

## Part 6 — Configure your settings

1. In your SSH terminal, run:
   ```
   cp .env.example .env
   nano .env
   ```
   This opens a simple text editor showing your settings.
2. Using your arrow keys to move around, fill in these values (replace the blank/example values with your own — don't touch the lines you don't recognize):
   - `BOT_TOKEN=` → paste the token from Part 1, step 7
   - `BOT_USERNAME=` → your bot's username from Part 1, step 6 (without the @)
   - `JWT_SECRET=` → type any long random sentence of letters and numbers (e.g. `xk29Plq8zM3vRt71Bq`)
   - `ADMIN_USERNAME=` → the username you'll use to log into the admin panel (e.g. `admin`)
   - `ADMIN_PASSWORD=` → a strong password for the admin panel
3. When done, press **Ctrl+O** then **Enter** to save, then **Ctrl+X** to exit.

---

## Part 7 — Launch the platform

In your SSH terminal, run:

```
docker compose up -d --build
```

This will take a few minutes the first time — it's downloading and building everything. When it
finishes, you'll be back at the command prompt.

Check everything is running:
```
docker compose ps
```
You should see `postgres`, `redis`, `bot`, `worker`, `web`, and `nginx` all listed as "Up" or "running".

---

## Part 8 — Create your admin login

Run:
```
docker compose run --rm web npm run seed:admin
```
You should see a message like `Created admin user "admin". You can now log in at /admin/login.`

---

## Part 9 — Log into the admin panel

1. Open a web browser and go to: `http://YOUR_SERVER_IP:3000/admin/login`
   (Once you set up a free subdomain + HTTPS in the "Going live" section below, use
   `https://yourdomain/admin/login` instead — no port number needed.)
2. Enter the `ADMIN_USERNAME` and `ADMIN_PASSWORD` you set in Part 6.
3. You should land on the **Dashboard**.

---

## Part 10 — Register your channel and group

1. In the admin panel sidebar, click **Channels**.
2. Fill in the form:
   - **Shard key:** `channel-01`
   - **Telegram chat ID:** paste the Channel Chat ID from Part 2
   - **Invite link:** paste the channel invite link from Part 2
3. Click **Add Channel Shard**.
4. Click **Groups** in the sidebar and repeat with your group's chat ID and invite link, using shard key `group-01`.

---

## Part 11 — Test it yourself

1. Open your bot's chat in Telegram (search its username).
2. Since this is your first user, you won't have a referral link yet — that's expected for testing. Ask a friend to message your bot using a referral link once you've generated one, **or** temporarily test the flow by having a second Telegram account message your bot with a link shaped like `t.me/YourBotUsername?start=REF_XXXXXXXX` (you'll only have real codes after your first real signup completes).
3. Share your phone number when prompted, join the channel and group links the bot sends you, then tap **"I joined both"**.
4. Send `/status` to see your referral code and current standing.
   (The numbers come from a daily cache that also refreshes once right when the worker starts up
   — so you'll see real numbers within a few seconds of Part 7, not a full 24-hour wait.)
5. Send `/bankdetails` to test the payout-account flow.

---

## Part 12 — Running the monthly payout

**Eligibility rule:** a referral only counts toward a given month's payout if that referred person
became **active on or before the 15th of that month** (Indian time). Someone who joins and
activates on, say, the 23rd simply carries over and counts starting *next* month instead — this is
automatic, you don't need to track it yourself.

Around the **30th of each month** (the worker also tries to run this automatically that day, but
you can always trigger it manually):
1. Go to **Payouts** in the admin panel.
2. Enter the month (format `YYYY-MM`) and a rate between ₹1 and ₹5.
3. Click **Save Rate**, then **Run Monthly Payout**.
4. Review the list on screen, then choose an export:
   - **Export Bulk Bank Upload CSV** — the one you'll actually use for paying people. It's
     formatted for your bank's bulk-transfer tool (beneficiary name, account number, IFSC, UPI
     fallback, amount, a reference note) and only includes people who both owe money and have
     already added a payment method.
   - **Full detail CSV** — every row with status, for your own records.
   - **Missing bank details** — anyone who's owed money but hasn't sent `/bankdetails` to the bot
     yet, so you know who to message.
5. Upload the bulk CSV to your bank's bulk-transfer portal (or process manually) and pay everyone.
6. Come back to the admin panel, enter each person's transaction reference, and click **Mark Paid**.

---

## Going live with a free subdomain (recommended — no domain purchase needed)

You don't need to buy a domain. This project is already set up to run off **one single
free subdomain**, using paths instead of separate subdomains for the bot webhook, website, and
admin panel.

### Get a free subdomain
1. Go to **duckdns.org** and sign in (Google/GitHub/etc. login).
2. Choose a subdomain name, e.g. `myreferralapp` → this gives you `myreferralapp.duckdns.org`.
3. In the "current ip" box, enter your server's IP address (from Part 3) and click **update ip**.
   (FreeDNS at afraid.org or noip.com work the same way if you prefer those.)

### Point everything at it
1. On your server, edit your settings again:
   ```
   nano .env
   ```
2. Set:
   ```
   BOT_WEBHOOK_URL=https://myreferralapp.duckdns.org
   NEXT_PUBLIC_SITE_URL=https://myreferralapp.duckdns.org
   ```
   (replace with your actual DuckDNS subdomain). Save with **Ctrl+O**, Enter, then **Ctrl+X**.

### Add HTTPS (the padlock)

Since Nginx runs inside Docker here (not installed directly on the system), we use Certbot's
**webroot** method, which works alongside the running container with no downtime.

1. Make sure your `.env` changes from above are saved, then apply them and create the shared
   folder Certbot will use:
   ```
   mkdir -p certbot-webroot
   docker compose up -d --build
   ```
2. Install Certbot:
   ```
   sudo apt-get install -y certbot
   ```
3. Request your certificate (replace both the domain and the email with your own):
   ```
   sudo certbot certonly --webroot -w ~/telegram-referral-platform/certbot-webroot \
     -d myreferralapp.duckdns.org --email you@example.com --agree-tos --non-interactive
   ```
   If successful, it prints where your certificate was saved
   (`/etc/letsencrypt/live/myreferralapp.duckdns.org/`).
4. Activate the HTTPS Nginx config — this command copies the HTTPS template over your current
   config and fills in your real domain automatically:
   ```
   sed "s/YOURDOMAIN/myreferralapp.duckdns.org/g" nginx/nginx-https.conf.template > nginx/nginx.conf
   docker compose restart nginx
   ```
5. Visit `https://myreferralapp.duckdns.org` — you should see the padlock.

### Keep the certificate renewing automatically

Let's Encrypt certificates expire every 90 days. Set up a scheduled renewal so you never have to
think about it again:
```
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f ~/telegram-referral-platform/docker-compose.yml exec nginx nginx -s reload") | crontab -
```
This checks daily at 3am and silently renews + reloads Nginx only when the certificate is actually
close to expiring.

### Restart everything
```
docker compose up -d --build
```

Once this finishes, your platform is live at:
- **Website:** `https://myreferralapp.duckdns.org`
- **Admin panel:** `https://myreferralapp.duckdns.org/admin/login`
- **Bot webhook:** handled automatically at `https://myreferralapp.duckdns.org/webhook`

No separate subdomains, no domain purchase, no ongoing cost beyond your server.

### If you'd rather buy a real domain later
Buy any domain (Namecheap, GoDaddy, etc.), point its **A record** at your server's IP instead of
using DuckDNS, and use the exact same steps above with your own domain in place of the DuckDNS one.

---

## If something goes wrong

- **Nothing loads in the browser:** run `docker compose ps` — if a service isn't "Up", run `docker compose logs <service-name>` (e.g. `docker compose logs bot`) to see the error.
- **Bot doesn't respond:** double check `BOT_TOKEN` in `.env` has no extra spaces, then run `docker compose up -d --build bot`.
- **Membership checks fail:** confirm your bot is an **admin** in both the channel and the group (Part 2).
- Any time you change `.env`, re-run `docker compose up -d --build` for the change to take effect.

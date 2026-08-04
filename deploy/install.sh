#!/usr/bin/env bash
# Idempotent installer for a fresh Ubuntu 24.04 box (Ampere A1 / ARM64).
# Run as root:  sudo bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/referral
APP_USER=referral
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip nginx ufw tzdata openssl

echo "==> Creating service user and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$APP_DIR/data"

if [ "$REPO_DIR" != "$APP_DIR" ]; then
    echo "==> Copying application to $APP_DIR"
    cp -r "$REPO_DIR/app" "$REPO_DIR/deploy" "$REPO_DIR/requirements.txt" "$APP_DIR/"
fi

echo "==> Building the virtualenv"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
    echo "==> Writing a starter .env (edit it before starting the service!)"
    cp "$REPO_DIR/.env.example" "$APP_DIR/.env"
    sed -i "s|^DB_PATH=.*|DB_PATH=$APP_DIR/data/referral.db|" "$APP_DIR/.env"
    sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=$(openssl rand -hex 24)|" "$APP_DIR/.env"
    sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=$(openssl rand -hex 24)|" "$APP_DIR/.env"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"

echo "==> Installing the systemd unit"
cp "$APP_DIR/deploy/referral.service" /etc/systemd/system/referral.service
systemctl daemon-reload
systemctl enable referral

echo "==> Installing the nginx site"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/referral
ln -sf /etc/nginx/sites-available/referral /etc/nginx/sites-enabled/referral
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat <<EOF

Done. Next:

  1. Edit $APP_DIR/.env  — BOT_TOKENS, ADMIN_IDS, PUBLIC_BASE_URL.
     Your generated admin token is:
       $(grep '^ADMIN_TOKEN=' "$APP_DIR/.env" | cut -d= -f2)
  2. Set server_name in /etc/nginx/sites-available/referral, then:
       nginx -t && systemctl reload nginx
  3. systemctl start referral && journalctl -u referral -f
  4. Open http://<your-domain>/admin

Remember to open ports 80 and 443 in the Oracle Cloud security list too —
ufw alone is not enough on Oracle instances.
EOF

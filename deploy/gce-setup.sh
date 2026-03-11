#!/usr/bin/env bash
# =============================================================================
# ByteBit Backend — GCE One-Time VM Bootstrap
# =============================================================================
# 1. Clone the repo FIRST, then run this script from inside it:
#
#   git clone https://github.com/Ashvita9/ByteBit-backend.git
#   sudo bash ByteBit-backend/deploy/gce-setup.sh
#
# After this script finishes:
#   1. Fill in /opt/bytebit/.env  (MONGO_URI, DJANGO_SECRET_KEY, etc.)
#   2. sudo systemctl enable --now bytebit-backend
#   3. sudo systemctl reload nginx
# =============================================================================
set -euo pipefail

# Resolve the repo root from this script's own location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_SRC="$SCRIPT_DIR"

APP_HOME="/opt/bytebit"
APP_REPO="$APP_HOME/app"
VENV="$APP_HOME/venv"
APP_USER="bytebit"
DEST_DIR="$APP_REPO/ByteBit-backend"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ByteBit GCE Bootstrap"
echo " Source: $BACKEND_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. System packages ────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y software-properties-common

# Ubuntu 22.04 ships Python 3.10 by default; Django 6.x requires Python 3.12.
# deadsnakes PPA is the standard way to get 3.12 on 22.04.
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    nginx redis-server \
    git curl ufw build-essential

# Start + enable Redis
systemctl enable --now redis-server
echo "✓ Redis running on 127.0.0.1:6379"

# ── 2. Firewall (allow SSH + HTTP + HTTPS) ────────────────────────────────────
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
echo "✓ UFW firewall configured"

# ── 3. Create a dedicated non-root user ───────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    echo "✓ OS user '$APP_USER' created"
else
    echo "ℹ OS user '$APP_USER' already exists"
fi

# Let the app user reload the service without a password (needed for deploy.sh)
echo "$APP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart bytebit-backend, /bin/systemctl reload nginx" \
    > /etc/sudoers.d/bytebit-backend
chmod 440 /etc/sudoers.d/bytebit-backend

# ── 4. Copy repo to its permanent home ───────────────────────────────────────
mkdir -p "$APP_REPO"
if [ "$(realpath "$BACKEND_DIR")" = "$(realpath "$DEST_DIR" 2>/dev/null || echo NONE)" ]; then
    echo "ℹ Repo already at $DEST_DIR, skipping copy"
else
    cp -a "$BACKEND_DIR" "$DEST_DIR"
    echo "✓ Repo copied to $DEST_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_HOME"
echo "✓ Ownership set on $APP_HOME"

# From here on use DEST_DIR as the canonical path
BACKEND_DIR="$DEST_DIR"
DEPLOY_SRC="$BACKEND_DIR/deploy"

# ── 5. Python virtual environment + dependencies ──────────────────────────────
sudo -u "$APP_USER" python3.12 -m venv "$VENV"
sudo -u "$APP_USER" "$VENV/bin/pip" install --upgrade pip wheel -q
sudo -u "$APP_USER" "$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
echo "✓ Python venv at $VENV"

# ── 6. Place the .env placeholder ────────────────────────────────────────────
if [ ! -f "$APP_HOME/.env" ]; then
    cp "$DEPLOY_SRC/gce.env.example" "$APP_HOME/.env"
    chown "$APP_USER:$APP_USER" "$APP_HOME/.env"
    chmod 600 "$APP_HOME/.env"
    echo ""
    echo "⚠  IMPORTANT: Fill in $APP_HOME/.env before starting the service!"
    echo ""
else
    echo "ℹ .env already exists, not overwriting"
fi

# ── 7. Collect static files (can run before .env is finalised — uses defaults) ─
cd "$BACKEND_DIR"
sudo -u "$APP_USER" env \
    DJANGO_SETTINGS_MODULE=backend.settings \
    DJANGO_SECRET_KEY=placeholder-build-key \
    DEBUG=False \
    "$VENV/bin/python" manage.py collectstatic --no-input -v 0
echo "✓ Static files collected"

# ── 8. Install systemd service ────────────────────────────────────────────────
cp "$DEPLOY_SRC/bytebit-backend.service" /etc/systemd/system/bytebit-backend.service
systemctl daemon-reload
echo "✓ systemd service installed (not started yet)"

# ── 9. Install Nginx config ───────────────────────────────────────────────────
cp "$DEPLOY_SRC/nginx.conf" /etc/nginx/sites-available/bytebit-backend
ln -sf /etc/nginx/sites-available/bytebit-backend /etc/nginx/sites-enabled/bytebit-backend
rm -f /etc/nginx/sites-enabled/default   # remove default placeholder
nginx -t && echo "✓ Nginx config valid"
systemctl enable nginx

# ── 10. SSH key for GitHub Actions deploys ────────────────────────────────────
# Creates a dedicated deploy key pair in the bytebit user's home.
# Add the PUBLIC key contents to: GCE VM → ~/.ssh/authorized_keys
# Add the PRIVATE key as the GitHub secret GCE_SSH_KEY.
DEPLOY_KEY="$APP_HOME/.ssh/deploy_ed25519"
mkdir -p "$APP_HOME/.ssh"
chown "$APP_USER:$APP_USER" "$APP_HOME/.ssh"
chmod 700 "$APP_HOME/.ssh"

if [ ! -f "$DEPLOY_KEY" ]; then
    sudo -u "$APP_USER" ssh-keygen -t ed25519 -f "$DEPLOY_KEY" -N "" -C "bytebit-github-actions"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Deploy key generated."
    echo " PUBLIC KEY (add to authorized_keys on this VM):"
    cat "${DEPLOY_KEY}.pub"
    echo ""
    echo " PRIVATE KEY (add as GitHub secret GCE_SSH_KEY):"
    cat "$DEPLOY_KEY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Auto-authorise the key on this VM
    cat "${DEPLOY_KEY}.pub" >> "$APP_HOME/.ssh/authorized_keys"
    chmod 600 "$APP_HOME/.ssh/authorized_keys"
    chown "$APP_USER:$APP_USER" "$APP_HOME/.ssh/authorized_keys"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Bootstrap complete. Next steps:"
echo ""
echo " 1. sudo nano $APP_HOME/.env"
echo "    → fill in DJANGO_SECRET_KEY, MONGO_URI (required)"
echo " 2. sudo -u bytebit bash -c 'set -a; source $APP_HOME/.env; set +a;\
echo "     $VENV/bin/python $BACKEND_DIR/manage.py migrate --run-syncdb'"
echo " 3. sudo systemctl enable --now bytebit-backend"
echo " 4. sudo systemctl reload nginx"
echo " 5. curl http://35.200.152.58/api/health/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

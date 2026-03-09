#!/usr/bin/env bash
# =============================================================================
# ByteBit Backend — Hot Deploy Script
# =============================================================================
# Runs ON the GCE VM as the 'bytebit' user.
# Called automatically by GitHub Actions on every push to main.
#
# Manual run:  bash /opt/bytebit/app/ByteBit-backend/deploy/deploy.sh
# =============================================================================
set -euo pipefail

APP_HOME="/opt/bytebit"
APP_REPO="$APP_HOME/app"
BACKEND_DIR="$APP_REPO/ByteBit-backend"
VENV="$APP_HOME/venv"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ByteBit Deploy  [$TIMESTAMP]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Pull latest code ───────────────────────────────────────────────────────
echo "→ Pulling latest code..."
cd "$APP_REPO"
git fetch --all --prune
git reset --hard origin/main
echo "  Commit: $(git log -1 --format='%h %s (%an)')"

# ── 2. Install / update Python dependencies ───────────────────────────────────
echo "→ Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q

# ── 3. Load env and run Django management commands ───────────────────────────
echo "→ Running Django management commands..."
cd "$BACKEND_DIR"

# Source the .env so management commands can reach MongoDB / Redis
set -a
# shellcheck source=/dev/null
[ -f "$APP_HOME/.env" ] && source "$APP_HOME/.env"
set +a

"$VENV/bin/python" manage.py collectstatic --no-input -v 0
"$VENV/bin/python" manage.py migrate --run-syncdb

# ── 4. Restart the ASGI service ───────────────────────────────────────────────
echo "→ Restarting bytebit-backend service..."
sudo /bin/systemctl restart bytebit-backend

# ── 5. Verify the service came up ─────────────────────────────────────────────
sleep 3
if systemctl is-active --quiet bytebit-backend; then
    echo "  ✓ Service is running"
else
    echo "  ✗ Service failed to start! Check: sudo journalctl -u bytebit-backend -n 50"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Deploy complete  [$TIMESTAMP]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

#!/usr/bin/env bash
# =============================================================================
# ByteBit Backend — Hot Deploy Script
# =============================================================================
set -euo pipefail

APP_DIR="/opt/bytebit/app/ByteBit-backend"
VENV="/opt/bytebit/venv"
ENV_FILE="/opt/bytebit/.env"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ByteBit Deploy  [$TIMESTAMP]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Pull latest code ───────────────────────────────────────────────────────
echo "→ Pulling latest code..."
cd "$APP_DIR"
git fetch --all --prune
git reset --hard origin/main
echo "  Commit: $(git log -1 --format='%h %s (%an)')"

# ── 2. Install / update Python dependencies ───────────────────────────────────
echo "→ Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# ── 3. Load env and run Django management commands ───────────────────────────
echo "→ Running Django management commands..."
cd "$APP_DIR"

# Source the .env so management commands can reach MongoDB / Redis
set -a
[ -f "$ENV_FILE" ] && source "$ENV_FILE"
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

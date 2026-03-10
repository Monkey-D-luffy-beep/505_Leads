#!/bin/bash
# =============================================================================
# Outbound Tool — Deployment Script
# Run this on your Oracle Cloud VM after SSH-ing in.
# Usage: ./deploy.sh
# =============================================================================

set -e

APP_DIR="/home/ubuntu/outbound-tool"
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"

echo "============================================"
echo "  Outbound Tool — Deploying..."
echo "  $(date)"
echo "============================================"

# 1. Pull latest code
echo ""
echo "[1/6] Pulling latest code..."
cd "$APP_DIR"
git pull origin main

# 2. Activate venv and install deps
echo ""
echo "[2/6] Installing Python dependencies..."
cd "$BACKEND_DIR"
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet

# 3. Install Playwright browsers (if needed)
echo ""
echo "[3/6] Ensuring Playwright browsers are installed..."
playwright install chromium 2>/dev/null || echo "  Playwright already installed or not needed"

# 4. Restart services
echo ""
echo "[4/6] Restarting services..."
sudo systemctl restart outbound-api
sudo systemctl restart outbound-worker
sudo systemctl restart outbound-beat

# 5. Wait and check health
echo ""
echo "[5/6] Checking health..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)

if [ "$HTTP_CODE" == "200" ]; then
    echo "  ✅ API is healthy (HTTP $HTTP_CODE)"
else
    echo "  ❌ API returned HTTP $HTTP_CODE — check logs:"
    echo "     sudo journalctl -u outbound-api -n 30"
fi

# 6. Show service statuses
echo ""
echo "[6/6] Service statuses:"
echo "  API:    $(systemctl is-active outbound-api)"
echo "  Worker: $(systemctl is-active outbound-worker)"
echo "  Beat:   $(systemctl is-active outbound-beat)"
echo "  Redis:  $(systemctl is-active redis-server)"

echo ""
echo "============================================"
echo "  Deployment complete at $(date)"
echo "============================================"

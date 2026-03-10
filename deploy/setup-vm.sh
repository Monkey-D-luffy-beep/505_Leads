#!/bin/bash
# =============================================================================
# Outbound Tool — Initial VM Setup Script
# Run this ONCE on a fresh Oracle Cloud Ubuntu 22.04 ARM VM.
# Usage: sudo bash setup-vm.sh
# =============================================================================

set -e

echo "============================================"
echo "  Outbound Tool — VM Initial Setup"
echo "  $(date)"
echo "============================================"

# 1. System update
echo ""
echo "[1/8] Updating system packages..."
apt update && apt upgrade -y

# 2. Install dependencies
echo ""
echo "[2/8] Installing system dependencies..."
apt install -y python3.11 python3.11-venv python3-pip \
    git nginx certbot python3-certbot-nginx \
    redis-server build-essential curl software-properties-common

# 3. Install Node.js 20.x (for frontend tooling if needed)
echo ""
echo "[3/8] Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 4. Start and enable Redis
echo ""
echo "[4/8] Configuring Redis..."
systemctl enable redis-server
systemctl start redis-server

# 5. Configure firewall
echo ""
echo "[5/8] Configuring firewall..."
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw --force enable

# 6. Clone repo and setup backend
echo ""
echo "[6/8] Setting up backend..."
cd /home/ubuntu
if [ ! -d "outbound-tool" ]; then
    echo "  ⚠ Please clone your repo manually:"
    echo "    git clone https://github.com/yourusername/outbound-tool.git"
    echo "  Then re-run this script."
else
    cd outbound-tool/backend
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "  ✅ Backend dependencies installed"

    # Install Playwright browsers
    pip install playwright
    playwright install chromium
    playwright install-deps chromium
fi

# 7. Install systemd services
echo ""
echo "[7/8] Installing systemd services..."
DEPLOY_DIR="/home/ubuntu/outbound-tool/deploy/systemd"
if [ -d "$DEPLOY_DIR" ]; then
    cp "$DEPLOY_DIR/outbound-api.service" /etc/systemd/system/
    cp "$DEPLOY_DIR/outbound-worker.service" /etc/systemd/system/
    cp "$DEPLOY_DIR/outbound-beat.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable outbound-api outbound-worker outbound-beat
    echo "  ✅ Systemd services installed and enabled"
else
    echo "  ⚠ deploy/systemd directory not found — copy service files manually"
fi

# 8. Setup Nginx
echo ""
echo "[8/8] Setting up Nginx..."
NGINX_CONF="/home/ubuntu/outbound-tool/deploy/nginx/outbound-api.conf"
if [ -f "$NGINX_CONF" ]; then
    cp "$NGINX_CONF" /etc/nginx/sites-available/outbound-api
    ln -sf /etc/nginx/sites-available/outbound-api /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
    echo "  ✅ Nginx configured"
    echo "  ⚠ Remember to edit /etc/nginx/sites-available/outbound-api"
    echo "    and replace api.yourdomain.com with your actual domain"
    echo "    Then run: sudo certbot --nginx -d api.yourdomain.com"
else
    echo "  ⚠ Nginx config not found — configure manually"
fi

echo ""
echo "============================================"
echo "  Initial setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Clone your repo (if not done)"
echo "  2. Copy .env.example to .env and fill in values"
echo "  3. Run: python scripts/seed_signals.py"
echo "  4. Edit Nginx config with your domain"
echo "  5. Run: sudo certbot --nginx -d api.yourdomain.com"
echo "  6. Start services: sudo systemctl start outbound-api outbound-worker outbound-beat"
echo "  7. Deploy frontend to Vercel"
echo "============================================"

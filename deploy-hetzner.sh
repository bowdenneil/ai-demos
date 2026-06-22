#!/bin/bash
# AI Demos Portal — Hetzner Deployment Script
# Run this after setting HCLOUD_TOKEN

set -euo pipefail

SERVER_NAME="ai-demos"
SERVER_TYPE="cx22"
LOCATION="fsn1"  # Falkenstein, Germany
IMAGE="ubuntu-24.04"
SSH_KEY_NAME="neil-ai-demos"

echo "=== AI Demos Portal — Hetzner Deployment ==="

# 1. Check for API token
if [ -z "${HCLOUD_TOKEN:-}" ]; then
  echo "ERROR: Set HCLOUD_TOKEN first:"
  echo "  export HCLOUD_TOKEN=your_token_here"
  exit 1
fi

# 2. Register SSH key
echo ">>> Registering SSH key..."
SSH_PUB=$(cat ~/.ssh/id_ed25519.pub)
if hcloud ssh-key list | grep -q "$SSH_KEY_NAME"; then
  echo "    SSH key already registered"
else
  hcloud ssh-key create --name "$SSH_KEY_NAME" --public-key "$SSH_PUB"
  echo "    SSH key registered"
fi

# 3. Create server
echo ">>> Creating $SERVER_NAME ($SERVER_TYPE in $LOCATION)..."
if hcloud server list | grep -q "$SERVER_NAME"; then
  echo "    Server already exists"
else
  hcloud server create \
    --name "$SERVER_NAME" \
    --type "$SERVER_TYPE" \
    --location "$LOCATION" \
    --image "$IMAGE" \
    --ssh-key "$SSH_KEY_NAME"
fi

SERVER_IP=$(hcloud server ip "$SERVER_NAME")
echo ">>> Server IP: $SERVER_IP"

# 4. Wait for server to be reachable
echo ">>> Waiting for server to boot..."
for i in $(seq 1 30); do
  if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 root@$SERVER_IP echo "up" 2>/dev/null; then
    break
  fi
  sleep 5
  echo "    attempt $i/30..."
done

# 5. Deploy the app
echo ">>> Deploying AI Demos Portal..."
ssh root@$SERVER_IP 'bash -s' << 'REMOTE_SCRIPT'
set -e

# System setup
apt-get update && apt-get install -y python3 python3-pip nginx certbot python3-certbot-nginx git

# Create app user
useradd -m -s /bin/bash ai-demos || true

# Clone repo
cd /home/ai-demos
if [ -d ai-demos ]; then
  cd ai-demos && git pull
else
  sudo -u ai-demos git clone https://github.com/bowdenneil/ai-demos.git
  cd ai-demos
fi

# Install Python deps
pip3 install --break-system-packages requests 2>/dev/null || true

# Create systemd service
cat > /etc/systemd/system/ai-demos.service << 'EOF'
[Unit]
Description=AI Demos Portal
After=network.target

[Service]
Type=simple
User=ai-demos
WorkingDirectory=/home/ai-demos/ai-demos
ExecStart=/usr/bin/python3 server.py --port 8888
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-demos
systemctl restart ai-demos

# Wait for service to start
sleep 2
if ! systemctl is-active --quiet ai-demos; then
  echo "ERROR: Service failed to start"
  journalctl -u ai-demos --no-pager -n 20
  exit 1
fi

# Nginx config
cat > /etc/nginx/sites-available/ai-demos << 'NGINX'
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE/streaming support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
NGINX

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/ai-demos /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo ">>> Server setup complete!"
REMOTE_SCRIPT

echo ""
echo "============================================"
echo "  AI Demos Portal deployed!"
echo "  URL: http://$SERVER_IP"
echo ""
echo "  Next steps:"
echo "  1. Point a domain A record at $SERVER_IP"
echo "  2. Run: ssh root@$SERVER_IP certbot --nginx -d yourdomain.com"
echo "  3. Login: neil.bowden@dell.com / PugHermes2026!"
echo "============================================"

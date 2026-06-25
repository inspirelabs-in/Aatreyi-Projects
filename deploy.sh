#!/bin/bash
# Run this script on your Oracle Cloud (or any Ubuntu) server.
# It installs Docker, pulls the repo, and starts all services.
#
# Usage:
#   1. SSH into the server
#   2. Upload this script:  scp deploy.sh ubuntu@YOUR_IP:~/
#   3. Run:                 bash deploy.sh

set -e

echo "=== Installing Docker ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to re-login for group changes to take effect."
else
    echo "Docker already installed."
fi

echo "=== Cloning repo ==="
REPO_DIR="/opt/tga"
if [ ! -d "$REPO_DIR" ]; then
    sudo git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git $REPO_DIR
    sudo chown -R $USER:$USER $REPO_DIR
else
    echo "Repo already exists at $REPO_DIR, pulling latest..."
    cd $REPO_DIR && git pull
fi

cd $REPO_DIR

echo ""
echo "=== REQUIRED: Copy your secrets to the server ==="
echo "From your LOCAL machine, run:"
echo "  scp .env ubuntu@YOUR_IP:/opt/tga/.env"
echo "  scp tga_user.session ubuntu@YOUR_IP:/opt/tga/tga_user.session"
echo ""
echo "Press ENTER once done (or Ctrl+C to abort and copy first)..."
read

if [ ! -f ".env" ]; then
    echo "ERROR: .env not found at $REPO_DIR/.env"
    exit 1
fi

if [ ! -f "tga_user.session" ]; then
    echo "ERROR: tga_user.session not found at $REPO_DIR/tga_user.session"
    exit 1
fi

echo "=== Starting services ==="
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "=== Done! ==="
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo "Your demo is live at: http://$SERVER_IP"
echo ""
echo "To view logs:  docker compose logs -f"
echo "To stop:       docker compose down"

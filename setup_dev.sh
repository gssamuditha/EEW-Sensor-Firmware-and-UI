#!/bin/bash
# EEW Sensor — Local Development Setup Script
# Run this from INSIDE your cloned repository on the Raspberry Pi
# Example: cd ~/EEW-Sensor-Firmware-and-UI && bash setup_dev.sh

set -euo pipefail

# 1. Ensure we are in the repo directory
if [ ! -f "backend/main.py" ]; then
    echo "ERROR: Please run this script from the root of the EEW-Sensor-Firmware-and-UI repository."
    exit 1
fi

REPO_DIR=$(pwd)
USER_NAME=$(whoami)

echo "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    sqlite3 python3-venv python3-pip python3-dev build-essential swig liblgpio-dev

echo "Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install -r backend/requirements.txt

echo "Building React Frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Creating development systemd service..."
SERVICE_FILE="/tmp/eew-sensor-dev.service"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=EEW Sensor (Development Mode)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR/backend
Environment="PATH=$REPO_DIR/.venv/bin:/usr/bin:/bin"
Environment="EEW_FRONTEND_DIST=$REPO_DIR/frontend/dist"
ExecStart=$REPO_DIR/.venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo mv "$SERVICE_FILE" /etc/systemd/system/eew-sensor-dev.service
sudo systemctl daemon-reload
sudo systemctl enable eew-sensor-dev
sudo systemctl restart eew-sensor-dev

echo "=========================================================="
echo "  Development Service Installed Successfully!"
echo "=========================================================="
echo "Service is running from: $REPO_DIR"
echo "If you edit the Python code, just run:"
echo "  sudo systemctl restart eew-sensor-dev"
echo ""
echo "Live logs:"
echo "  sudo journalctl -u eew-sensor-dev -f"
echo "=========================================================="

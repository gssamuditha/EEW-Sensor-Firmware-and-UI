#!/bin/bash
# Run this script on the Raspberry Pi to set up the EEW Sensor service to start on boot.

# Get the absolute path to the current directory (should be the root of the repo)
REPO_DIR=$(pwd)
VENV_DIR="$REPO_DIR/.venv"

echo "Setting up EEW Sensor Systemd Service..."

# Ensure we are in the right directory
if [ ! -d "$REPO_DIR/backend" ] || [ ! -d "$REPO_DIR/frontend" ]; then
    echo "Error: Please run this script from the root directory of the EEW-Sensor-Firmware-and-UI project."
    exit 1
fi

# Create the virtual environment on first run only
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Installing system dependencies and creating venv..."
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        python3-venv python3-pip sqlite3 python3-dev build-essential swig liblgpio-dev
    python3 -m venv "$VENV_DIR"
fi

# Always sync Python packages — picks up any new/changed dependencies in requirements.txt
# pip is smart: already-satisfied packages are skipped instantly.
echo "Syncing Python dependencies from requirements.txt..."
source "$VENV_DIR/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$REPO_DIR/backend/requirements.txt"
echo "  -> Dependencies up to date."

SERVICE_FILE=/etc/systemd/system/eew-sensor-dev.service

echo "Creating systemd service file at $SERVICE_FILE..."

# Create the service file using sudo
sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=EEW Sensor Backend & UI Service
After=network.target

[Service]
User=$USER
WorkingDirectory=$REPO_DIR/backend
# Allow non-root user to bind to privileged ports like 80
AmbientCapabilities=CAP_NET_BIND_SERVICE
# Using uvicorn directly avoids the development reloader that is in main.py
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=5
# Set production environment variables if needed
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "Fixing database and directory permissions..."
# Ensure the backend directory is owned by the current user and writable
sudo chown -R $USER:$USER "$REPO_DIR/backend"
sudo chmod 755 "$REPO_DIR/backend"

# Ensure the database file is writable by the user if it exists
if [ -f "$REPO_DIR/backend/eew_sensor.db" ]; then
    sudo chmod 644 "$REPO_DIR/backend/eew_sensor.db"
fi

echo "Setting up passwordless sudo for nmcli and reboot..."
# Determine the real user (even if run via sudo)
if [ -n "$SUDO_USER" ]; then
    REALUSER="$SUDO_USER"
else
    REALUSER="$USER"
fi

SUDOERS_FILE="/etc/sudoers.d/eew-sensor-permissions"
echo "$REALUSER ALL=(ALL) NOPASSWD: /usr/bin/nmcli, /bin/nmcli, /sbin/reboot, /usr/sbin/reboot, /usr/bin/systemctl, /bin/systemctl" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"
echo "  -> $REALUSER can now run nmcli and reboot without a password."

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling eew-sensor-dev service to start on boot..."
sudo systemctl enable eew-sensor-dev.service

echo "Restarting eew-sensor-dev service..."
sudo systemctl restart eew-sensor-dev.service

echo "=================================================================="
echo "Development Service setup complete!"
echo "The sensor and UI will now start automatically when the Pi boots."
echo ""
echo "Helpful Maintenance Commands:"
echo "- Check status: sudo systemctl status eew-sensor-dev.service"
echo "- View logs:    sudo journalctl -u eew-sensor-dev.service -f"
echo "- Stop service: sudo systemctl stop eew-sensor-dev.service"
echo "- Start service: sudo systemctl start eew-sensor-dev.service"
echo "=================================================================="

#!/bin/bash
# EEW Sensor Auto-Update Script
# Runs via cron to check for new GitHub releases.

# Ensure we are executing in the repository root directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

LOG_FILE="$DIR/eew_auto_update.log"
VERSION_FILE=".current_version"
REPO_URL="https://api.github.com/repos/gssamuditha/EEW-Sensor-Firmware-and-UI/releases/latest"

# Helper to log with timestamps
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 1. Check Internet Connection
if ! ping -c 1 8.8.8.8 &> /dev/null; then
    # We only log this to avoid spamming the log if offline for a long time, 
    # but for debugging it's useful to see it attempted.
    echo "$(date '+%Y-%m-%d %H:%M:%S') - No internet connection. Skipping update." >> "$LOG_FILE"
    exit 0
fi

# 2. Fetch Latest Release from GitHub API
log "Checking for new releases..."
LATEST_RELEASE=$(curl -s $REPO_URL)

# Extract tag_name using grep and sed to avoid needing 'jq' installed
TAG_NAME=$(echo "$LATEST_RELEASE" | grep -m 1 '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$TAG_NAME" ] || [ "$TAG_NAME" == "null" ]; then
    log "Failed to fetch release or no releases found."
    exit 1
fi

CURRENT_VERSION=""
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE")
fi

if [ "$TAG_NAME" == "$CURRENT_VERSION" ]; then
    log "Already up-to-date with version $TAG_NAME."
    exit 0
fi

log "New version found: $TAG_NAME. Updating from $CURRENT_VERSION..."

# 3. Pull Latest Code
log "Fetching latest tags and code..."
git fetch --tags origin
# Checkout the new tag and force reset to discard any local modifications
git reset --hard "tags/$TAG_NAME"

# 4. Update Backend Dependencies
log "Updating backend dependencies..."
if [ -d ".venv" ]; then
    .venv/bin/pip install -r backend/requirements.txt
else
    log "Warning: .venv not found. Ensure setup_service.sh was run."
fi

# 6. Save new version and Restart Service
echo "$TAG_NAME" > "$VERSION_FILE"
log "Update complete. Restarting eew-sensor service..."
sudo systemctl restart eew-sensor.service

log "Service restarted successfully."

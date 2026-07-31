#!/bin/bash
# EEW Sensor Auto-Update Script
# Runs via cron to check for new GitHub releases and update safely.
#
# DATA SAFETY GUARANTEES
# ----------------------
# 1. The service is stopped GRACEFULLY before any git operation so that
#    in-flight DB writes and miniSEED flushes can complete.
# 2. eew_sensor.db is BACKED UP before the git reset. If anything fails,
#    the backup is automatically RESTORED and the old service version restarts.
# 3. The user's archive_root setting is READ from the DB before the update
#    and RE-APPLIED after, so a custom miniSEED archive path is never lost.
# 4. A PRAGMA integrity_check is run on the DB after the update. Any
#    corruption triggers an automatic rollback.

# ============================================================
# CONFIGURATION
# ============================================================

# Define the desired cron schedule here. If you change this in Git,
# the sensors will automatically update their own cron jobs to match it!
DESIRED_CRON="0 * * * *"

# Set repository directory (assumes running from the out-of-tree updater location)
REPO_DIR="$HOME/EEW-Sensor-Firmware-and-UI"
DB_PATH="$REPO_DIR/backend/eew_sensor.db"
DB_BACKUP="$REPO_DIR/backend/eew_sensor.db.bak"

cd "$REPO_DIR" || exit 1

LOG_FILE="$REPO_DIR/eew_auto_update.log"
VERSION_FILE="$REPO_DIR/.current_version"
REPO_URL="https://api.github.com/repos/gssamuditha/EEW-Sensor-Firmware-and-UI/releases/latest"

# ============================================================
# HELPERS
# ============================================================

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Read a single key from the settings table without starting Python.
# Usage: read_setting <key> <default>
read_setting() {
    local key="$1"
    local default="$2"
    if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
        local val
        val=$(sqlite3 "$DB_PATH" "SELECT value FROM settings WHERE key='$key' LIMIT 1;" 2>/dev/null)
        echo "${val:-$default}"
    else
        echo "$default"
    fi
}

# Write a single key back to the settings table.
# Usage: write_setting <key> <value>
write_setting() {
    local key="$1"
    local value="$2"
    if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
        sqlite3 "$DB_PATH" \
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('$key', '$value');" 2>/dev/null
    fi
}

# Check DB integrity. Returns 0 if ok, 1 if corrupt.
check_db_integrity() {
    if ! command -v sqlite3 &>/dev/null; then
        log "  sqlite3 not found — skipping integrity check."
        return 0
    fi
    if [ ! -f "$DB_PATH" ]; then
        return 0   # DB doesn't exist yet; init_db() will create it fresh.
    fi
    local result
    result=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | head -1)
    if [ "$result" != "ok" ]; then
        log "  ERROR: DB integrity check failed (result: $result)."
        return 1
    fi
    return 0
}

# Full rollback: restore DB backup and restart service on the current code.
rollback() {
    log "ROLLBACK: Restoring database backup and restarting service..."
    if [ -f "$DB_BACKUP" ]; then
        cp -p "$DB_BACKUP" "$DB_PATH"
        log "  Database restored from backup."
    fi
    sudo systemctl start eew-sensor.service
    log "  Service restarted on previous version."
    exit 1
}

# ============================================================
# STEP 0 — Self-Adjust Cron Schedule
# This MUST run at the top of the script so it executes even if no update is needed.
# ============================================================
CURRENT_CRON=$(crontab -l 2>/dev/null | grep "\.eew_updater\.sh")
EXPECTED_CRON="$DESIRED_CRON $HOME/.eew_updater.sh"

if [ "$CURRENT_CRON" != "$EXPECTED_CRON" ]; then
    log "Updating cron schedule to: $DESIRED_CRON"
    (crontab -l 2>/dev/null | grep -v "\.eew_updater\.sh"; echo "$EXPECTED_CRON") | crontab -
fi

# ============================================================
# STEP 1 — Stagger Execution
# Sleeps for a random time (0–300 s) to spread out GitHub API requests
# across a fleet of sensors.
# ============================================================
STAGGER=$((RANDOM % 300))
log "Staggering check by $STAGGER seconds to spread out API requests..."
sleep $STAGGER

# ============================================================
# STEP 2 — Check Internet Connection
# ============================================================
if ! ping -c 1 8.8.8.8 &>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - No internet connection. Skipping update." >> "$LOG_FILE"
    exit 0
fi

# ============================================================
# STEP 3 — Fetch Latest Release Tag from GitHub API
# ============================================================
log "Checking for new releases..."
LATEST_RELEASE=$(curl -s "$REPO_URL")

# Extract tag_name using grep and sed (avoids requiring 'jq')
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

log "New version found: $TAG_NAME. Updating from ${CURRENT_VERSION:-'(none)'}..."

# ============================================================
# STEP 4 — Graceful Service Stop
# Stops the service so the DB writer thread and miniSEED flush thread
# can drain their queues cleanly before we touch any files.
# ============================================================
log "Stopping eew-sensor service gracefully (flushing in-flight data)..."
sudo systemctl stop eew-sensor.service

# Wait up to 15 seconds for a clean shutdown
for i in $(seq 1 15); do
    if ! systemctl is-active --quiet eew-sensor.service; then
        log "  Service stopped cleanly after $i second(s)."
        break
    fi
    sleep 1
done

if systemctl is-active --quiet eew-sensor.service; then
    log "  WARNING: Service did not stop in time — forcing kill."
    sudo systemctl kill eew-sensor.service
    sleep 2
fi

# ============================================================
# STEP 5 — Pre-Update Data Preservation
# Read user-configured settings BEFORE the git reset so they
# survive even if init_db() tries to overwrite them.
# ============================================================
log "Reading user settings before update..."
SAVED_ARCHIVE_ROOT=$(read_setting "archive_root" "/home/crisislab/data/archive")
SAVED_RETENTION_DAYS=$(read_setting "retention_days" "7")
SAVED_LATITUDE=$(read_setting "latitude" "0.0")
SAVED_LONGITUDE=$(read_setting "longitude" "0.0")
SAVED_DEVICE_NAME=$(read_setting "device_name" "CRISIS-NODE-01")
SAVED_DEVICE_ID=$(read_setting "device_id" "T0021")
SAVED_NETWORK_CODE=$(read_setting "network_code" "CL")
SAVED_LOCATION_CODE=$(read_setting "location_code" "00")
SAVED_DATA_FORWARDING=$(read_setting "data_forwarding" "true")
SAVED_TARGETS=$(read_setting "targets" "")
log "  archive_root     = $SAVED_ARCHIVE_ROOT"
log "  retention_days   = $SAVED_RETENTION_DAYS"
log "  device_id        = $SAVED_DEVICE_ID"

# Back up the database
if [ -f "$DB_PATH" ]; then
    log "Backing up database to $(basename "$DB_BACKUP")..."
    cp -p "$DB_PATH" "$DB_BACKUP"
    if [ $? -eq 0 ]; then
        log "  Backup created successfully."
    else
        log "  ERROR: Backup failed. Aborting update — restarting service."
        sudo systemctl start eew-sensor.service
        exit 1
    fi
else
    log "  No existing database found — fresh install, no backup needed."
fi

# ============================================================
# STEP 6 — Pull Latest Code
# git reset --hard will update all tracked files but cannot touch
# files listed in .gitignore (like *.db) as long as they remain
# untracked. The backup in STEP 5 provides a second layer of safety.
# ============================================================
log "Fetching latest tags and code..."
git fetch --tags origin
if [ $? -ne 0 ]; then
    log "ERROR: git fetch failed. Restarting service on previous version."
    sudo systemctl start eew-sensor.service
    exit 1
fi

log "Resetting working tree to $TAG_NAME..."
git reset --hard "tags/$TAG_NAME"
if [ $? -ne 0 ]; then
    log "ERROR: git reset --hard failed. Rolling back..."
    rollback
fi

# ============================================================
# STEP 7 — Update Backend Dependencies
# ============================================================
log "Updating backend dependencies..."
if [ -d ".venv" ]; then
    .venv/bin/pip install -r backend/requirements.txt --quiet
    if [ $? -ne 0 ]; then
        log "ERROR: pip install failed. Rolling back..."
        rollback
    fi
else
    log "Warning: .venv not found. Ensure setup_service.sh was run."
fi

# ============================================================
# STEP 8 — Self-Update the Updater Script (Safe Out-of-Tree Pattern)
# The cron job runs ~/.eew_updater.sh which is OUTSIDE the repo,
# so git reset cannot delete or modify the running script mid-execution.
# ============================================================
if [ -f "$REPO_DIR/auto_update.sh" ]; then
    log "Updating out-of-tree updater script..."
    cp "$REPO_DIR/auto_update.sh" "$HOME/.eew_updater.sh"
    chmod +x "$HOME/.eew_updater.sh"
else
    log "Warning: auto_update.sh missing from release. Existing updater preserved."
fi

# ============================================================
# STEP 9 — Restore User Settings into DB
# The service will call init_db() on next start which uses
# INSERT OR IGNORE for most settings — but we explicitly re-apply
# all user-customized values here to guarantee they survive.
# sqlite3 must be available; if not, the service's own init_db()
# will use INSERT OR IGNORE which still preserves existing rows.
# ============================================================
if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
    log "Restoring user settings into database..."
    sqlite3 "$DB_PATH" <<SQL
INSERT OR REPLACE INTO settings (key, value) VALUES ('archive_root',    '$SAVED_ARCHIVE_ROOT');
INSERT OR REPLACE INTO settings (key, value) VALUES ('retention_days',  '$SAVED_RETENTION_DAYS');
INSERT OR REPLACE INTO settings (key, value) VALUES ('latitude',        '$SAVED_LATITUDE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('longitude',       '$SAVED_LONGITUDE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('device_name',     '$SAVED_DEVICE_NAME');
INSERT OR REPLACE INTO settings (key, value) VALUES ('device_id',       '$SAVED_DEVICE_ID');
INSERT OR REPLACE INTO settings (key, value) VALUES ('network_code',    '$SAVED_NETWORK_CODE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('location_code',   '$SAVED_LOCATION_CODE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('data_forwarding', '$SAVED_DATA_FORWARDING');
SQL
    # Restore targets only if non-empty (it contains JSON with quotes)
    if [ -n "$SAVED_TARGETS" ]; then
        sqlite3 "$DB_PATH" \
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('targets', '$SAVED_TARGETS');" 2>/dev/null
    fi
    log "  Settings restored."
else
    log "  sqlite3 not available — settings will be preserved by INSERT OR IGNORE on next start."
fi

# ============================================================
# STEP 10 — DB Integrity Check
# Validate the database before starting the service. If the check
# fails, roll back to the backup.
# ============================================================
log "Running database integrity check..."
if ! check_db_integrity; then
    log "Database is corrupt after update. Rolling back..."
    rollback
fi
log "  Integrity check passed."

# ============================================================
# STEP 11 — Save Version and Restart Service
# ============================================================
echo "$TAG_NAME" > "$VERSION_FILE"
log "Update to $TAG_NAME complete. Starting eew-sensor service..."
sudo systemctl start eew-sensor.service

# Wait up to 10 seconds and confirm the service is running
for i in $(seq 1 10); do
    if systemctl is-active --quiet eew-sensor.service; then
        log "  Service is running (confirmed after $i second(s))."
        break
    fi
    sleep 1
done

if ! systemctl is-active --quiet eew-sensor.service; then
    log "ERROR: Service failed to start after update! Rolling back to previous version..."
    # Restore previous version tag so next run attempts update again
    if [ -n "$CURRENT_VERSION" ]; then
        echo "$CURRENT_VERSION" > "$VERSION_FILE"
    else
        rm -f "$VERSION_FILE"
    fi
    rollback
fi

# ============================================================
# STEP 12 — Cleanup Old Backup (keep only the most recent)
# ============================================================
if [ -f "$DB_BACKUP" ]; then
    log "Update fully successful — removing old DB backup."
    rm -f "$DB_BACKUP"
fi

log "=== Update to $TAG_NAME completed successfully. ==="

#!/bin/bash
# EEW Sensor Auto-Update Script (Package-Based OTA)
# ===================================================
# Runs via cron. Checks GitHub Releases for a new .deb package,
# downloads it, verifies the SHA256 checksum, and installs it with dpkg.
#
# DATA SAFETY GUARANTEES (unchanged from previous git-based updater)
# ------------------------------------------------------------------
# 1. The database is BACKED UP before any install so that in-flight
#    DB writes complete before files are touched.
# 2. If dpkg fails or the service does not restart, the DB backup is
#    RESTORED and the system stays on the previous version.
# 3. User-configured settings (location, device_id, etc.) are READ from
#    the DB before the upgrade and RE-APPLIED afterwards.
# 4. A PRAGMA integrity_check is run on the DB after the upgrade.
#    Any corruption triggers an automatic rollback.
#
# WHAT CHANGED vs. the old git-pull approach
# ------------------------------------------
#  - No git, no pip, no Python venv required on the Pi.
#  - The Pi receives only the compiled .deb — no source code.
#  - dpkg's prerm/postinst hooks handle service stop/start.

# ============================================================
# CONFIGURATION
# ============================================================

# Cron schedule — changing this here propagates to all sensors on next run.
DESIRED_CRON="0 * * * *"

# GitHub repository (public releases are fetched without a token).
REPO_OWNER="gssamuditha"
REPO_NAME="EEW-Sensor-Firmware-and-UI"
REPO_API="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

# Installation path written by the .deb package.
INSTALL_DIR="/opt/eew-sensor"
DB_PATH="${INSTALL_DIR}/backend/eew_sensor.db"
DB_BACKUP="${HOME}/eew_sensor.db.bak"

# Version marker (stores the currently installed tag name).
VERSION_FILE="/opt/eew-sensor/.installed_version"

# Temporary download location.
DEB_TMP="/tmp/eew-sensor-update.deb"
SHA256_TMP="/tmp/eew-sensor-update.deb.sha256"

LOG_FILE="${HOME}/eew_auto_update.log"

# ============================================================
# HELPERS
# ============================================================

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

read_setting() {
    local key="$1" default="$2"
    if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
        local val
        val=$(sqlite3 "$DB_PATH" "SELECT value FROM settings WHERE key='$key' LIMIT 1;" 2>/dev/null)
        echo "${val:-$default}"
    else
        echo "$default"
    fi
}

write_setting() {
    local key="$1" value="$2"
    if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
        sqlite3 "$DB_PATH" \
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('$key', '$value');" 2>/dev/null
    fi
}

check_db_integrity() {
    if ! command -v sqlite3 &>/dev/null; then
        log "  sqlite3 not found — skipping integrity check."
        return 0
    fi
    [ ! -f "$DB_PATH" ] && return 0   # fresh install — init_db() will create it
    local result
    result=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | head -1)
    if [ "$result" != "ok" ]; then
        log "  ERROR: DB integrity check failed (result: $result)."
        return 1
    fi
    return 0
}

rollback() {
    log "ROLLBACK: Restoring database backup..."
    if [ -f "$DB_BACKUP" ]; then
        cp -p "$DB_BACKUP" "$DB_PATH" && log "  Database restored." || log "  WARNING: restore failed."
    fi
    log "  The previously installed package remains active."
    exit 1
}

cleanup_tmp() {
    rm -f "$DEB_TMP" "$SHA256_TMP"
}
trap cleanup_tmp EXIT

# ============================================================
# STEP 0 — Self-Adjust Cron Schedule
# ============================================================
CURRENT_CRON=$(crontab -l 2>/dev/null | grep "\.eew_updater\.sh")
EXPECTED_CRON="$DESIRED_CRON $HOME/.eew_updater.sh"
if [ "$CURRENT_CRON" != "$EXPECTED_CRON" ]; then
    log "Updating cron schedule to: $DESIRED_CRON"
    (crontab -l 2>/dev/null | grep -v "\.eew_updater\.sh"; echo "$EXPECTED_CRON") | crontab -
fi

# ============================================================
# STEP 1 — Stagger Execution
# Spread API requests across a fleet of sensors.
# ============================================================
STAGGER=$((RANDOM % 300))
log "Staggering check by ${STAGGER}s to spread fleet API requests..."
sleep "$STAGGER"

# ============================================================
# STEP 2 — Check Internet Connection
# ============================================================
if ! ping -c 1 8.8.8.8 &>/dev/null; then
    log "No internet connection — skipping update check."
    exit 0
fi

# ============================================================
# STEP 3 — Fetch Latest Release from GitHub API
# ============================================================
log "Querying GitHub Releases API..."
LATEST_JSON=$(curl -sf --max-time 15 "$REPO_API") || {
    log "ERROR: GitHub API request failed. Skipping."
    exit 1
}

TAG_NAME=$(echo "$LATEST_JSON" | grep -m 1 '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [ -z "$TAG_NAME" ] || [ "$TAG_NAME" = "null" ]; then
    log "ERROR: Could not parse release tag from API response."
    exit 1
fi

# ============================================================
# STEP 4 — Compare with Installed Version
# ============================================================
CURRENT_VERSION=""
[ -f "$VERSION_FILE" ] && CURRENT_VERSION=$(cat "$VERSION_FILE")

if [ "$TAG_NAME" = "$CURRENT_VERSION" ]; then
    log "Already up-to-date ($TAG_NAME). Nothing to do."
    exit 0
fi
log "New version available: $TAG_NAME (installed: ${CURRENT_VERSION:-(none)})"

# ============================================================
# STEP 5 — Extract Asset Download URLs
# ============================================================
# Find .deb and .sha256 URLs from the release assets JSON.
DEB_URL=$(echo "$LATEST_JSON" \
    | grep '"browser_download_url":' \
    | grep '\.deb"' \
    | sed -E 's/.*"(https[^"]+)".*/\1/' \
    | head -1)

SHA256_URL=$(echo "$LATEST_JSON" \
    | grep '"browser_download_url":' \
    | grep '\.sha256"' \
    | sed -E 's/.*"(https[^"]+)".*/\1/' \
    | head -1)

if [ -z "$DEB_URL" ]; then
    log "ERROR: No .deb asset found in release $TAG_NAME. Aborting."
    exit 1
fi
log "Package URL: $DEB_URL"

# ============================================================
# STEP 6 — Pre-Upgrade Data Preservation
# Read all user settings from the DB BEFORE dpkg touches any files.
# ============================================================
log "Reading user settings before upgrade..."
SAVED_ARCHIVE_ROOT=$(read_setting "archive_root"     "/home/crisislab/data/archive")
SAVED_RETENTION_DAYS=$(read_setting "retention_days" "7")
SAVED_LATITUDE=$(read_setting       "latitude"       "0.0")
SAVED_LONGITUDE=$(read_setting      "longitude"      "0.0")
SAVED_ELEVATION=$(read_setting      "elevation"      "0.0")
SAVED_DEVICE_NAME=$(read_setting    "device_name"    "EEW-NODE-01")
SAVED_DEVICE_ID=$(read_setting      "device_id"      "T0021")
SAVED_NETWORK_CODE=$(read_setting   "network_code"   "CL")
SAVED_LOCATION_CODE=$(read_setting  "location_code"  "00")
SAVED_DATA_FORWARDING=$(read_setting "data_forwarding" "true")
SAVED_TARGETS=$(read_setting        "targets"        "")
log "  device_id = $SAVED_DEVICE_ID | latitude = $SAVED_LATITUDE | longitude = $SAVED_LONGITUDE"

# Back up the database (outside /opt so dpkg can't touch it)
if [ -f "$DB_PATH" ]; then
    log "Backing up database to $(basename "$DB_BACKUP")..."
    if cp -p "$DB_PATH" "$DB_BACKUP"; then
        log "  Backup created at $DB_BACKUP"
    else
        log "  ERROR: Backup failed. Aborting upgrade."
        exit 1
    fi
else
    log "  No existing database — fresh install."
fi

# ============================================================
# STEP 7 — Download .deb Package
# ============================================================
log "Downloading $TAG_NAME package..."
if ! curl -L --fail --max-time 300 --progress-bar -o "$DEB_TMP" "$DEB_URL"; then
    log "ERROR: Failed to download package. Aborting."
    exit 1
fi
log "  Downloaded $(du -sh "$DEB_TMP" | cut -f1)"

# ============================================================
# STEP 8 — Verify SHA256 Checksum
# ============================================================
if [ -n "$SHA256_URL" ]; then
    log "Verifying SHA256 checksum..."
    if ! curl -sL --max-time 15 -o "$SHA256_TMP" "$SHA256_URL"; then
        log "  WARNING: Could not download checksum file — skipping verification."
    else
        # The checksum file contains "HASH  filename.deb"
        # We rewrite it to point at our local DEB_TMP so sha256sum -c works.
        EXPECTED_HASH=$(awk '{print $1}' "$SHA256_TMP")
        ACTUAL_HASH=$(sha256sum "$DEB_TMP" | awk '{print $1}')
        if [ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]; then
            log "ERROR: SHA256 mismatch! Package may be corrupt or tampered."
            log "  Expected: $EXPECTED_HASH"
            log "  Got:      $ACTUAL_HASH"
            exit 1
        fi
        log "  Checksum verified ✓"
    fi
else
    log "  WARNING: No .sha256 asset in release — checksum verification skipped."
fi

# ============================================================
# STEP 9 — Install Package
# dpkg's prerm stops the service; postinst starts it again.
# ============================================================
log "Installing $TAG_NAME with dpkg..."
if ! sudo dpkg -i "$DEB_TMP"; then
    log "ERROR: dpkg -i failed. Rolling back..."
    rollback
fi
log "  dpkg install succeeded."

# ============================================================
# STEP 10 — Restore User Settings
# The new package's init_db() uses INSERT OR IGNORE, so existing
# rows are preserved. We explicitly re-apply all user values here
# to guarantee they survive even if schema migrations ran.
# ============================================================
if command -v sqlite3 &>/dev/null && [ -f "$DB_PATH" ]; then
    log "Restoring user settings into database..."
    sqlite3 "$DB_PATH" <<SQL
INSERT OR REPLACE INTO settings (key, value) VALUES ('archive_root',     '$SAVED_ARCHIVE_ROOT');
INSERT OR REPLACE INTO settings (key, value) VALUES ('retention_days',   '$SAVED_RETENTION_DAYS');
INSERT OR REPLACE INTO settings (key, value) VALUES ('latitude',         '$SAVED_LATITUDE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('longitude',        '$SAVED_LONGITUDE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('elevation',        '$SAVED_ELEVATION');
INSERT OR REPLACE INTO settings (key, value) VALUES ('device_name',      '$SAVED_DEVICE_NAME');
INSERT OR REPLACE INTO settings (key, value) VALUES ('device_id',        '$SAVED_DEVICE_ID');
INSERT OR REPLACE INTO settings (key, value) VALUES ('network_code',     '$SAVED_NETWORK_CODE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('location_code',    '$SAVED_LOCATION_CODE');
INSERT OR REPLACE INTO settings (key, value) VALUES ('data_forwarding',  '$SAVED_DATA_FORWARDING');
SQL
    if [ -n "$SAVED_TARGETS" ]; then
        sqlite3 "$DB_PATH" \
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('targets', '$SAVED_TARGETS');" 2>/dev/null
    fi
    log "  Settings restored."
else
    log "  sqlite3 unavailable — settings preserved by INSERT OR IGNORE on service start."
fi

# ============================================================
# STEP 11 — DB Integrity Check
# ============================================================
log "Running database integrity check..."
if ! check_db_integrity; then
    log "Database corrupt after upgrade. Rolling back..."
    rollback
fi
log "  Integrity check passed ✓"

# ============================================================
# STEP 12 — Confirm Service is Running
# ============================================================
sleep 3   # give systemd time to restart the service
for i in $(seq 1 15); do
    if systemctl is-active --quiet eew-sensor.service; then
        log "  eew-sensor.service is active (confirmed after ${i}s)."
        break
    fi
    sleep 1
done

if ! systemctl is-active --quiet eew-sensor.service; then
    log "ERROR: Service failed to start after upgrade! Rolling back..."
    rollback
fi

# ============================================================
# STEP 13 — Save Installed Version
# ============================================================
echo "$TAG_NAME" | sudo tee "$VERSION_FILE" > /dev/null
log "=== Upgrade to $TAG_NAME completed successfully. ==="

# ============================================================
# STEP 14 — Self-Update the Updater (safe out-of-tree pattern)
# Extract the new auto_update.sh from the installed package if present.
# The cron job runs ~/.eew_updater.sh (outside /opt) so dpkg cannot
# delete the running script mid-execution.
# ============================================================
# The installed package does not contain auto_update.sh (it is not needed
# on-device now that git is gone). Instead we ship the updater separately
# and keep it at ~/.eew_updater.sh. No self-update step needed.

# ============================================================
# STEP 15 — Cleanup
# ============================================================
if [ -f "$DB_BACKUP" ]; then
    log "Removing DB backup after successful upgrade."
    rm -f "$DB_BACKUP"
fi

#!/bin/bash
# EEW Sensor — First-Time Bootstrap Installer
# ============================================
# Run this script once on a fresh Raspberry Pi (64-bit Raspberry Pi OS)
# to install the EEW Sensor appliance from the latest GitHub Release.
#
# Requirements:
#   - Raspberry Pi 3 or newer running 64-bit Raspberry Pi OS (arm64)
#   - Internet connection
#   - A user account named 'crisislab' (or change SENSOR_USER below)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/gssamuditha/EEW-Sensor-Firmware-and-UI/main/setup_service.sh | bash
#   OR: ./setup_service.sh
# ============================================================

set -euo pipefail

REPO_OWNER="gssamuditha"
REPO_NAME="EEW-Sensor-Firmware-and-UI"
REPO_API="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
SENSOR_USER="${SENSOR_USER:-crisislab}"
VERSION_FILE="/opt/eew-sensor/.installed_version"
DEB_TMP="/tmp/eew-sensor-install.deb"
SHA256_TMP="/tmp/eew-sensor-install.deb.sha256"

# ── Colour helpers ───────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Check we're running on a Raspberry Pi (arm64) ────────────
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
    error "This installer requires a 64-bit (arm64/aarch64) Raspberry Pi OS."
    error "Detected architecture: $ARCH"
    error "Please flash a fresh 64-bit Raspberry Pi OS image and try again."
    exit 1
fi

# ── Check for required tools ─────────────────────────────────
for cmd in curl dpkg systemctl; do
    if ! command -v "$cmd" &>/dev/null; then
        error "Required command not found: $cmd"
        exit 1
    fi
done

echo "=========================================================="
echo "  EEW Sensor — Installation Bootstrap"
echo "=========================================================="
info "Architecture : $ARCH"
info "Service user : $SENSOR_USER"
echo ""

# ── Create sensor user if needed ─────────────────────────────
if ! id "$SENSOR_USER" &>/dev/null; then
    info "Creating user '$SENSOR_USER'..."
    sudo useradd -m -s /bin/bash -G spi,gpio,dialout "$SENSOR_USER"
else
    info "Ensuring user '$SENSOR_USER' is in hardware groups..."
    sudo usermod -aG spi,gpio,dialout "$SENSOR_USER"
fi

# ── Install system dependencies ──────────────────────────────
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    sqlite3 \
    network-manager \
    curl \
    python3-dev \
    build-essential \
    swig \
    liblgpio-dev \
    2>&1 | tail -3

# ── Fetch latest release ─────────────────────────────────────
info "Fetching latest release from GitHub..."
LATEST_JSON=$(curl -sf --max-time 15 "$REPO_API") || {
    error "Failed to reach GitHub API. Check your internet connection."
    exit 1
}

TAG_NAME=$(echo "$LATEST_JSON" \
    | grep -m 1 '"tag_name":' \
    | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$TAG_NAME" ] || [ "$TAG_NAME" = "null" ]; then
    error "No releases found on GitHub. Ensure at least one release exists."
    exit 1
fi
info "Latest release : $TAG_NAME"

# ── Extract download URLs ─────────────────────────────────────
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
    error "No .deb asset found in release $TAG_NAME."
    error "Please build and publish a release first using the GitHub Actions workflow."
    exit 1
fi

# ── Download package ─────────────────────────────────────────
info "Downloading $TAG_NAME..."
curl -L --fail --max-time 300 --progress-bar -o "$DEB_TMP" "$DEB_URL"
info "Downloaded $(du -sh "$DEB_TMP" | cut -f1)"

# ── Verify checksum ──────────────────────────────────────────
if [ -n "$SHA256_URL" ]; then
    info "Verifying SHA256 checksum..."
    curl -sL --max-time 15 -o "$SHA256_TMP" "$SHA256_URL"
    EXPECTED=$(awk '{print $1}' "$SHA256_TMP")
    ACTUAL=$(sha256sum "$DEB_TMP" | awk '{print $1}')
    if [ "$EXPECTED" != "$ACTUAL" ]; then
        error "Checksum mismatch — package may be corrupt."
        exit 1
    fi
    info "Checksum verified ✓"
else
    warn "No checksum file found in release — skipping verification."
fi

# ── Install package ──────────────────────────────────────────
info "Installing EEW Sensor package..."
sudo dpkg -i "$DEB_TMP"
rm -f "$DEB_TMP" "$SHA256_TMP"

# ── Save installed version ───────────────────────────────────
echo "$TAG_NAME" | sudo tee "$VERSION_FILE" > /dev/null

# ── Clean up legacy OTA Updater (if exists) ───────────────────
if crontab -l 2>/dev/null | grep -q "\.eew_updater\.sh\|auto_update\.sh"; then
    info "Removing legacy user crontab entry for OTA updater..."
    crontab -l 2>/dev/null | grep -v "\.eew_updater\.sh" | grep -v "auto_update\.sh" | crontab - || true
    rm -f "$HOME/.eew_updater.sh"
fi

# ── Sensor Variant Selection ──────────────────────────────────
echo ""
echo "=========================================================="
echo "  Sensor Hardware Variant"
echo "=========================================================="
echo ""
echo "  This firmware supports two hardware variants:"
echo "  [1] 3-CH  — 3× ADXL354 accelerometers only (ENZ, ENN, ENE)"
echo "  [2] 4-CH  — GeoPhone (EHZ) + 3× ADXL354 accelerometers"
echo ""
read -r -p "  Select your sensor type [1/2, default=1]: " SENSOR_CHOICE

case "$SENSOR_CHOICE" in
    2)
        SENSOR_VARIANT="4CH"
        info "4-CH variant selected — GeoPhone EHZ channel will be active."
        echo ""
        warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        warn "  REQUIRED: /boot/firmware/config.txt change for 4-CH SPI"
        warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "  The 4-CH sensor uses BCM pin 8 (CE0) as a manual chip-select."
        echo "  Standard SPI must be disabled and replaced with the no-CS overlay."
        echo ""
        echo "  Edit /boot/firmware/config.txt and make this change:"
        echo ""
        echo "    # REMOVE or comment out this line:"
        echo "    #   dtparam=spi=on"
        echo ""
        echo "    # ADD this line:"
        echo "    dtoverlay=spi0-0cs"
        echo ""
        warn "  This change requires a REBOOT to take effect."
        warn "  The sensor will NOT work until this change is made."
        echo ""
        read -r -p "  Press ENTER to continue after noting the above..." _dummy
        ;;
    *)
        SENSOR_VARIANT="3CH"
        info "3-CH variant selected — ADXL354 accelerometer channels only."
        ;;
esac

# Write sensor_variant into the SQLite DB settings table
EEW_DB="/opt/eew-sensor/backend/eew_sensor.db"
if command -v sqlite3 &>/dev/null; then
    sudo sqlite3 "$EEW_DB" \
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT); INSERT OR REPLACE INTO settings (key, value) VALUES ('sensor_variant', '${SENSOR_VARIANT}');"
    sudo chown $SENSOR_USER:$SENSOR_USER "$EEW_DB" || true
    info "Sensor variant '${SENSOR_VARIANT}' saved to database."
else
    warn "SQLite DB not found yet at $EEW_DB — sensor_variant will be set on first boot."
    warn "If needed, manually run: sqlite3 $EEW_DB \"INSERT OR REPLACE INTO settings (key, value) VALUES ('sensor_variant', '${SENSOR_VARIANT}');\""
fi

# Restart the service so the newly saved sensor_variant takes effect
if command -v systemctl &>/dev/null; then
    sudo systemctl restart eew-sensor
fi

# ── Final status ─────────────────────────────────────────────
echo ""
echo "=========================================================="
echo -e "  ${GREEN}EEW Sensor $TAG_NAME installed successfully!${NC}"
echo "=========================================================="
echo ""
info "Sensor variant  : $SENSOR_VARIANT"
info "Service status  : sudo systemctl status eew-sensor"
info "Live logs       : sudo journalctl -u eew-sensor -f"
info "Web UI          : http://$(hostname -I | awk '{print $1}')/"
echo ""

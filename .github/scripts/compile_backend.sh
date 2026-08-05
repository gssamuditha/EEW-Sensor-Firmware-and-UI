#!/usr/bin/env bash
# ============================================================
#  EEW Sensor — ARM64 Backend Compilation Script
#  Runs inside an ARM64 Docker container (via QEMU in CI).
#  Called by .github/workflows/build-release.yml
# ============================================================
set -euo pipefail

WORKSPACE="/workspace"
BACKEND="${WORKSPACE}/backend"
OUTPUT="${WORKSPACE}/build"

echo "=== System info ==="
uname -a
python3 --version

# ── System packages ─────────────────────────────────────────
echo "=== Installing system packages ==="
apt-get update -qq
apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    patchelf \
    ccache \
    libpam-dev \
    libglib2.0-dev \
    libdbus-1-dev \
    2>&1 | tail -5   # suppress verbose apt output

# ── Python packages ─────────────────────────────────────────
echo "=== Installing Python dependencies ==="
pip install --upgrade pip wheel setuptools --quiet

# Install Nuitka first
pip install nuitka --quiet

# Install all backend requirements.
# RPi.GPIO and spidev build from source — they compile on ARM even without Pi hardware.
# pamela needs libpam-dev (installed above).
pip install -r "${BACKEND}/requirements.txt" --quiet

# ── Nuitka compilation ───────────────────────────────────────
echo "=== Compiling with Nuitka (this takes 15–30 min on first run) ==="

mkdir -p "${OUTPUT}"

cd "${BACKEND}"

python -m nuitka \
    --standalone \
    --follow-imports \
    \
    --include-package=uvicorn \
    --include-package=fastapi \
    --include-package=starlette \
    --include-package=pydantic \
    --include-package=pydantic_core \
    --include-package=anyio \
    --include-package=sniffio \
    --include-package=scipy \
    --include-package=numpy \
    --include-package=obspy \
    --include-package=httpx \
    --include-package=httpcore \
    --include-package=psutil \
    --include-package=pamela \
    --include-package=multipart \
    \
    --noinclude-pytest-mode=nofollow \
    --noinclude-unittest-mode=nofollow \
    \
    --output-dir="${OUTPUT}" \
    run_server.py \
    2>&1

echo "=== Nuitka compilation done ==="

# Rename output directory to a stable name for artifact upload
mv "${OUTPUT}/run_server.dist" "${OUTPUT}/run_server.dist.final" 2>/dev/null || true
# GitHub artifact path in the workflow looks for build/run_server.dist/
[ -d "${OUTPUT}/run_server.dist.final" ] && mv "${OUTPUT}/run_server.dist.final" "${OUTPUT}/run_server.dist"

echo "=== Output directory contents ==="
ls -lh "${OUTPUT}/run_server.dist/"

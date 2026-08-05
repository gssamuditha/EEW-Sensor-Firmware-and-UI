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

echo "============================================================"
echo "=== System info ==="
uname -a && arch && python3 --version
echo "============================================================"

# ── System packages ─────────────────────────────────────────
# linux-libc-dev → provides <linux/spi/spidev.h> needed by spidev pip package
# libpam-dev     → required by pamela
# patchelf       → required by Nuitka to fix library RPATH entries
# ccache         → speeds up repeated Nuitka C compilations
echo "=== Installing system packages ==="
apt-get update -qq
apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    patchelf \
    ccache \
    libpam-dev \
    linux-libc-dev

echo "=== Installing Python dependencies ==="
pip install --upgrade pip wheel setuptools --root-user-action=ignore
pip install nuitka --root-user-action=ignore

# Install all backend requirements.
# sensor.py now uses _is_raspberry_pi() which checks /proc/device-tree/model.
# In this Docker container that file does NOT exist → use_mock=True at import time
# → RPi.GPIO / spidev are never instantiated → no RuntimeError during compilation.
pip install -r "${BACKEND}/requirements.txt" --root-user-action=ignore

echo "=== Compiling with Nuitka (15–40 min on first run) ==="
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
    run_server.py

echo "=== Nuitka compilation done ==="
echo "Output directory:"
ls -lh "${OUTPUT}/run_server.dist/"

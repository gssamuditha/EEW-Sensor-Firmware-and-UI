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
echo "============================================================"
uname -a
arch
python3 --version

# ── System packages ─────────────────────────────────────────
# linux-libc-dev   → provides <linux/spi/spidev.h> required by spidev pip package
# libpam-dev       → required by pamela
# patchelf         → required by Nuitka to fix library RPATH
# ccache           → speeds up repeated Nuitka C compilations
echo ""
echo "============================================================"
echo "=== Installing system packages ==="
echo "============================================================"
apt-get update -qq
apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    patchelf \
    ccache \
    libpam-dev \
    linux-libc-dev \
    libglib2.0-dev

echo ""
echo "============================================================"
echo "=== Installing Python dependencies ==="
echo "============================================================"
pip install --upgrade pip wheel setuptools

# Install Nuitka
pip install nuitka

# Install core Python packages (no hardware dependencies)
pip install \
    fastapi \
    "uvicorn[standard]" \
    websockets \
    pydantic \
    psutil \
    scipy \
    numpy \
    obspy \
    httpx \
    pamela

# Install hardware-specific packages separately.
# These compile fine on ARM Linux (the hardware check is runtime-only).
# spidev needs linux-libc-dev (installed above) for <linux/spi/spidev.h>.
echo "--- Installing hardware interface packages ---"
pip install spidev || {
    echo "WARNING: spidev failed to install. Creating stub module."
    python3 -c "
import os, textwrap
stub_dir = '${BACKEND}'
stub = textwrap.dedent('''
    # Auto-generated stub for cross-platform compilation
    class SpiDev:
        def open(self, *a, **kw): pass
        def xfer2(self, *a, **kw): return []
        def close(self): pass
        max_speed_hz = 0
        mode = 0
''')
with open(os.path.join(stub_dir, 'spidev.py'), 'w') as f:
    f.write(stub)
print('spidev stub created at ${BACKEND}/spidev.py')
"
}

pip install RPi.GPIO || {
    echo "WARNING: RPi.GPIO failed to install. Creating stub module."
    python3 -c "
import os, textwrap
stub_dir = '${BACKEND}'
os.makedirs(os.path.join(stub_dir, 'RPi'), exist_ok=True)
stub = textwrap.dedent('''
    # Auto-generated stub for cross-platform compilation
    BCM = 11; BOARD = 10; IN = 1; OUT = 0
    def setmode(*a, **kw): pass
    def setup(*a, **kw): pass
    def output(*a, **kw): pass
    def input(*a, **kw): return 0
    def cleanup(*a, **kw): pass
    def setwarnings(*a, **kw): pass
''')
with open(os.path.join(stub_dir, 'RPi', '__init__.py'), 'w') as f:
    f.write('')
with open(os.path.join(stub_dir, 'RPi', 'GPIO.py'), 'w') as f:
    f.write(stub)
print('RPi.GPIO stub created at ${BACKEND}/RPi/')
"
}

# ── Nuitka compilation ───────────────────────────────────────
echo ""
echo "============================================================"
echo "=== Compiling with Nuitka (15–40 min on first run) ==="
echo "============================================================"

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

echo ""
echo "============================================================"
echo "=== Nuitka compilation done ==="
echo "============================================================"

# Clean up any stubs we created so they don't get packaged
rm -f "${BACKEND}/spidev.py"
rm -rf "${BACKEND}/RPi"

echo "Output directory:"
ls -lh "${OUTPUT}/run_server.dist/"
echo "Done."

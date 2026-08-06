#!/usr/bin/env bash
# ============================================================
#  EEW Sensor — Backend Bytecode Compilation Script
#  Runs on a standard x86 GitHub Actions runner (ubuntu-latest).
#  Converts all Python source files to .pyc bytecode, then
#  removes the .py source. No ARM/QEMU/Docker needed.
# ============================================================
set -euo pipefail

BACKEND="/workspace/backend"
OUTPUT="/workspace/build/backend-dist"

echo "=== Python version ==="
python3.11 --version

echo "=== Compiling Python source to bytecode (.pyc) ==="
# Creates __pycache__/module.cpython-311.pyc for every .py file.
# Python 3.11 on the Pi can import these even without the .py source.
python3.11 -m compileall -q "$BACKEND"

echo "=== Building bytecode-only distribution ==="
mkdir -p "$OUTPUT"

# Copy the entire backend tree (includes __pycache__ with .pyc files)
cp -r "$BACKEND/." "$OUTPUT/"

# Delete Python source files — ship only .pyc bytecode
# Keep requirements.txt (needed for postinst pip install on the Pi)
find "$OUTPUT" -name "*.py" -delete

# Remove development-only directories
rm -rf "$OUTPUT/venv" "$OUTPUT/.venv" 2>/dev/null || true

echo "=== Distribution summary ==="
PYC=$(find "$OUTPUT" -name "*.pyc" | wc -l)
PY=$(find "$OUTPUT" -name "*.py" | wc -l)
echo "  .pyc files compiled : ${PYC}"
echo "  .py source remaining: ${PY}  (must be 0)"
if [ "$PY" -ne 0 ]; then
    echo "ERROR: Source files still present!"
    find "$OUTPUT" -name "*.py"
    exit 1
fi
echo "=== Done ==="

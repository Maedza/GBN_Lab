#!/usr/bin/env bash
set -e

echo "=== GBN Lab Setup ==="

# Find a working Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3 not found. Install it from https://python.org"
    exit 1
fi

echo "Using: $($PYTHON --version)"

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate & install
source venv/bin/activate
echo "Installing dependencies..."
pip install --quiet -r requirements.txt

echo ""
echo "Done. To run the simulator:"
echo "  source venv/bin/activate  # if not already active"
echo "  python main.py"

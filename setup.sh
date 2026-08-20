#!/usr/bin/env bash
set -e
# === GBN Lab — One-click Setup for macOS & Linux ===
# Usage:  ./setup.sh         (just install)
#         ./setup.sh run     (install + launch the simulator)

echo "====================================="
echo "  GBN Lab — Setup"
echo "====================================="

# ---- 1. Find Python 3 ----
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        v=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null || true)
        major=$(echo "$v" | sed 's/[^0-9,]/x/g' | cut -d',' -f1)
        if [ "$major" -ge 3 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    echo "ERROR: Python 3 not found."
    echo "  Install it from https://www.python.org/downloads/"
    echo "  (macOS: you can also run 'brew install python3')"
    exit 1
fi

echo "  Using: $($PYTHON --version)"

# ---- 2. Create virtual environment (if missing) ----
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    $PYTHON -m venv venv
fi

# ---- 3. Activate & install dependencies ----
source venv/bin/activate
echo "  Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "  Done! All dependencies installed."
echo ""

if [ "$1" = "run" ]; then
    echo "  Launching GBN Lab..."
    python app.py
else
    echo "  To launch the simulator:"
    echo ""
    echo "    source venv/bin/activate"
    echo "    python app.py"
    echo ""
    echo "  Or just:  ./setup.sh run"
fi

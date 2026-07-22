#!/usr/bin/env bash
# ============================================================================
# Confluence Trading Consultant - first-time installer (macOS / Linux)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo
echo "============================================================"
echo "  Confluence Trading Consultant - First-time setup"
echo "============================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not on PATH. Install Python 3.11+ from https://www.python.org/downloads/"
  read -rp "Press enter to exit..."
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node not on PATH. Install Node 18+ from https://nodejs.org/"
  read -rp "Press enter to exit..."
  exit 1
fi

# ---- Python venv
echo "[1/4] Python venv ..."
cd apps/api
[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip wheel setuptools >/dev/null

# ---- Backend deps
echo "[2/4] Backend deps (this may take a few minutes) ..."
pip install -r requirements.txt

# ---- Frontend deps
echo "[3/4] Frontend deps ..."
cd ../web
[ -d node_modules ] || npm install

# ---- Build frontend
echo "[4/4] Frontend production build ..."
[ -d .next ] || npm run build

cd ../..
echo
echo "============================================================"
echo "  Setup complete!"
echo
echo "  To start the app, run:   ./scripts/start.sh"
echo "============================================================"

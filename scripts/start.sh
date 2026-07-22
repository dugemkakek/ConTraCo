#!/usr/bin/env bash
# ============================================================================
# Confluence Trading Consultant - app starter (macOS / Linux)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=apps/api/venv
PYEXE="$VENV/bin/python"

if [ ! -x "$PYEXE" ]; then
  echo "First-time setup required."
  bash "$(dirname "$0")/install.sh"
  exit $?
fi

if [ ! -d apps/web/node_modules ]; then
  echo "First-time setup required."
  bash "$(dirname "$0")/install.sh"
  exit $?
fi

echo
echo "============================================================"
echo "  Confluence Trading Consultant"
echo
echo "  API: http://localhost:8000"
echo "  UI : http://localhost:3000  (opens automatically)"
echo
echo "  Logs: $(pwd)/logs/api.log, $(pwd)/logs/web.log"
echo "  Stop: Ctrl+C"
echo "============================================================"
echo

exec "$PYEXE" "$(pwd)/apps/api/dev_server.py" "$@"

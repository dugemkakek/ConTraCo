# One-Click Installers and Starters

The `scripts/` folder ships with everything you need to bring up the
Confluence Trading Consultant on a fresh machine.

## Files

| File | Purpose |
|---|---|
| `scripts\install.bat` / `scripts\install.sh` | First-time setup (Python venv, pip install, npm install, npm build). Idempotent — safe to re-run. |
| `scripts\start.bat` / `scripts\start.sh` | One-click app launcher. Auto-runs `install` if needed. Starts API + Web in a supervisor, opens browser to http://localhost:3000. |
| `scripts\start.cmd` | Minimal Windows launcher used as the target for desktop shortcuts. |
| `scripts\create_desktop_shortcut.ps1` | Drops a "Confluence Terminal" icon on the user's Desktop. |
| `apps\api\dev_server.py` | Supervises API + Web, tails logs, opens browser on launch, single Ctrl+C to stop both. |

## One-Click Quick Start (Windows)

1. Double-click **`scripts\install.bat`** once. Wait 3–5 minutes.
2. Double-click **`scripts\start.bat`** every subsequent session.
3. (Optional) Run **`scripts\create_desktop_shortcut.ps1`** to drop a
   desktop icon for step 2.

## One-Click Quick Start (macOS / Linux)

```bash
chmod +x scripts/*.sh
./scripts/install.sh           # first time only
./scripts/start.sh             # every subsequent run
```

## Manual Quick Start

If you don't want the wrappers:

```bash
# Backend
cd apps/api
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
RUN_MIGRATIONS_ON_STARTUP=1 uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd apps/web
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run build
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm start
```

## Custom Ports

```bash
# Linux/macOS
./scripts/start.sh --api-port 9000 --web-port 3001
```

```bat
:: Windows
scripts\start.bat --api-port 9000 --web-port 3001
```

## Logs

Service output is captured to:

- `logs\api.log`
- `logs\web.log`

Tail either file to debug.

## Stopping

Press Ctrl+C in the launcher window, or close the window.

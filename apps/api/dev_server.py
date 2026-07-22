"""Single-process supervisor for the ConTraCo app.

Brings up:
  * FastAPI (uvicorn) on :8000
  * Next.js production server (next start) on :3000
  * Opens the user's browser to http://localhost:3000

Logs go to ``logs/api.log`` and ``logs/web.log``. Both processes share
this console and can be stopped by Ctrl+C. Designed so the app is
reachable even if ``next start`` is unavailable — falls back to
``next dev`` if no build artifact is present.

Usage:
  python dev_server.py
  python dev_server.py --no-browser --api-port 8000 --web-port 3000
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent  # apps/api -> confluence-trading-consultant
LOG_DIR = PROJECT_ROOT / "logs"
API_PORT_DEFAULT = 8000
WEB_PORT_DEFAULT = 3000


def _ensure_logs_dir() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def _spawn(cmd: list[str], log_name: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.Popen:
    log_path = LOG_DIR / log_name
    log_path.parent.mkdir(exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    log_file.write(f"\n\n--- starting {log_name} @ {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        env=env or os.environ.copy(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _wait_for_url(url: str, timeout: float = 60.0) -> bool:
    """Poll URL until 2xx or timeout. Used so the browser waits for ready."""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            time.sleep(0.5)
    return False


def _vlc_python() -> str:
    """Path to the project venv Python. Falls back to system Python."""
    if os.name == "nt":
        candidate = ROOT / "venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / "venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _node_exe() -> str:
    return shutil.which("node") or shutil.which("nodejs") or "node"


def _npm_exe() -> str:
    return shutil.which("npm") or shutil.which("npm.cmd") or "npm"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=int(os.getenv("API_PORT", API_PORT_DEFAULT)))
    parser.add_argument("--web-port", type=int, default=int(os.getenv("WEB_PORT", WEB_PORT_DEFAULT)))
    parser.add_argument("--no-browser", action="store_true", help="skip opening browser on startup")
    parser.add_argument(
        "--mode",
        choices=("prod", "dev"),
        default=os.getenv("CONTRA_CO_MODE", "prod"),
        help="web mode (prod = next start after build; dev = next dev)",
    )
    args = parser.parse_args()

    _ensure_logs_dir()

    print(f"[supervisor] project: {PROJECT_ROOT}")
    print(f"[supervisor] api port : {args.api_port}")
    print(f"[supervisor] web port : {args.web_port}")
    print(f"[supervisor] web mode : {args.mode}")

    py = _vlc_python()
    node = _node_exe()
    npm = _npm_exe()

    api_cmd = [
        py, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(args.api_port),
        "--log-level", "info",
    ]
    print(f"[supervisor] api: {' '.join(api_cmd)}")
    api_proc = _spawn(api_cmd, "api.log", cwd=ROOT)

    web_dir = PROJECT_ROOT / "apps" / "web"
    if args.mode == "prod" and (web_dir / ".next").exists():
        web_cmd = [node, "node_modules/next/dist/bin/next", "start", "-p", str(args.web_port)]
    elif args.mode == "prod":
        # Fall back to dev if no build artifact exists.
        print("[supervisor] no build artifact (.next); falling back to next dev")
        web_cmd = [node, "node_modules/next/dist/bin/next", "dev", "-p", str(args.web_port)]
    else:
        web_cmd = [node, "node_modules/next/dist/bin/next", "dev", "-p", str(args.web_port)]

    # On Windows, npm-installed binaries are .cmd shims. Resolve them via npx
    # or shell. Use the `next` binary directly when next package is local.
    if not (web_dir / "node_modules" / "next" / "dist" / "bin" / "next").exists():
        web_cmd = [npm, "run", "start" if args.mode == "prod" else "dev", "--", "-p", str(args.web_port)]

    print(f"[supervisor] web: cd {web_dir} && {' '.join(web_cmd)}")
    web_proc = _spawn(web_cmd, "web.log", cwd=web_dir)

    api_url = f"http://localhost:{args.api_port}/health"
    web_url = f"http://localhost:{args.web_port}"

    print("[supervisor] waiting for services to be ready (up to 60s)...")
    api_ok = _wait_for_url(api_url, timeout=60)
    print(f"[supervisor] api ready: {api_ok} ({api_url})")
    web_ok = _wait_for_url(web_url, timeout=60)
    print(f"[supervisor] web ready: {web_ok} ({web_url})")

    if not args.no_browser:
        if web_ok:
            print(f"[supervisor] opening browser at {web_url}")
            try:
                webbrowser.open(web_url)
            except Exception as exc:  # noqa: BLE001
                print(f"[supervisor] browser launch skipped: {exc}")
        else:
            print("[supervisor] web not ready; tail logs/web.log")

    stop_event = {"flag": False}

    def _shutdown(*_):
        stop_event["flag"] = True

    if os.name == "nt":
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    else:
        import threading

        def _sig():
            _shutdown()

        threading.Thread(target=lambda: signal.signal(signal.SIGINT, _sig()), daemon=True).start()

    print("[supervisor] running (Ctrl+C to stop). Log files:")
    print(f"   - {(LOG_DIR / 'api.log')}")
    print(f"   - {(LOG_DIR / 'web.log')}")

    try:
        while not stop_event["flag"]:
            time.sleep(1)
            if api_proc.poll() is not None and not stop_event["flag"]:
                print(f"[supervisor] api exited (code {api_proc.returncode}); stopping")
                break
            if web_proc.poll() is not None and not stop_event["flag"]:
                print(f"[supervisor] web exited (code {web_proc.returncode}); stopping")
                break
    finally:
        print("[supervisor] shutting down child processes...")
        for proc in (api_proc, web_proc):
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()

    return 0


if __name__ == "__main__":
    sys.exit(main())

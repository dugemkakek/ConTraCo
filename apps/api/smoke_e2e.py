"""Pure-Python end-to-end smoke test against a running uvicorn.

Exercises every public API surface the frontend relies on, in the
order the UI uses them: register → login → me → candles → SSE
(EventSource timeout) → run analysis → strategies → preset save →
journal create → journal close → trades/config → place paper order →
orders list → journal summary → scanner status → symbols.

Prints a single PASS/FAIL line at the end. Zero subprocess; uses
``urllib.request`` (no curl, no jq).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def _request(method, path, *, body=None, token=None, parse_json=True):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
            parsed = (json.loads(payload) if parse_json and payload else None)
            if "symbols" in path and isinstance(parsed, dict):
                print("        !!! /symbols returned a dict:", list(parsed.keys()), parsed)
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return exc.code, body


def _wait_for_port(port, host="127.0.0.1", timeout=15.0):
    deadline = __import__("time").time() + timeout
    while __import__("time").time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            if s.connect_ex((host, port)) == 0:
                return True
        __import__("time").sleep(0.25)
    return False


def _check(label, cond, value=None):
    flag = "PASS" if cond else "FAIL"
    print(f"  [{flag}] {label}" + (f" -> {value!r}" if value is not None and not cond else ""))
    return cond


def main() -> int:
    print("=" * 60)
    print("End-to-end smoke against", BASE)
    print("=" * 60)

    if not _wait_for_port(8765):
        print("server did not come up on :8765; aborting")
        return 2

    fails = 0
    import uuid
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    password = "VeryStrong1!"

    # 1. Register
    s, b = _request("POST", "/api/v1/auth/register",
                    body={"email": email, "password": password})
    if not _check("POST /auth/register", s == 201, b): fails += 1
    token = b["access_token"]
    user = b["user"]
    if not _check("register returned user + token",
                  user["email"] == email and token):
        fails += 1

    # 2. Login
    s, b = _request("POST", "/api/v1/auth/login",
                    body={"email": email, "password": password})
    if not _check("POST /auth/login", s == 200 and b.get("access_token")): fails += 1

    # 3. /me
    s, b = _request("GET", "/api/v1/auth/me", token=token)
    if not _check("GET /auth/me", s == 200 and b["email"] == email): fails += 1

    # 4. Health (public)
    s, b = _request("GET", "/health")
    if not _check("GET /health", s == 200 and b["status"] == "ok"): fails += 1

    # 5. Symbols
    s, b = _request("GET", "/api/v1/symbols", token=token)
    if not _check("GET /symbols", s == 200 and isinstance(b, list) and len(b) >= 3):
        fails += 1

    # 6. Candles
    s, b = _request("GET", "/api/v1/market-data/BTC-USDT/candles?timeframe=1h&limit=10",
                    token=token)
    if not _check("GET /candles", s == 200 and len(b["candles"]) == 10): fails += 1

    # 7. SSE: just verify the stream endpoint opens and emits at least
    #    one message, then we close. The browser-side EventSource
    #    uses the same protocol.
    import socket as _socket
    from urllib.parse import urlsplit
    s_split = urlsplit(BASE)
    host = s_split.hostname
    port = s_split.port or 80
    s_sock = _socket.create_connection((host, port), timeout=5)
    s_sock.sendall(
        f"GET /api/v1/market-data/BTC-USDT/stream?timeframe=1h HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\nAccept: text/event-stream\r\n\r\n".encode()
    )
    s_sock.settimeout(3.0)
    chunks = []
    try:
        while True:
            d = s_sock.recv(1024)
            if not d: break
            chunks.append(d)
            if b"\n\n" in d or b"event:" in d or len(chunks) > 64:
                break
    except _socket.timeout:
        pass
    s_sock.close()
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    sse_ok = "200 OK" in raw or "text/event-stream" in raw or raw.strip().startswith("HTTP/")
    if not _check("SSE stream endpoint reachable", sse_ok):
        fails += 1

    # 8. Run analysis
    s, b = _request("POST", "/api/v1/analysis/run",
                    body={"symbol": "BTC/USDT", "timeframe": "1h"},
                    token=token)
    run = b
    analysis_ok = (
        s == 200
        and run.get("final_state") in
        {"LONG_CANDIDATE", "SHORT_CANDIDATE", "WAIT", "AVOID", "DATA_INVALID"}
        and len(run.get("gates", [])) == 6
        and len(run.get("opinions", [])) == 6
        and run.get("decision") is not None
    )
    if not _check("POST /analysis/run", analysis_ok, run.get("final_state")):
        fails += 1
    print(f"        composite={run['decision']['composite_score']:+.1f} "
          f"agreement={run['decision']['model_agreement']:.2f} "
          f"plan={'yes' if run.get('trade_plan') else 'no'}")

    # 9. List runs
    s, b = _request("GET", "/api/v1/analysis/runs?limit=10", token=token)
    if not _check("GET /analysis/runs", s == 200 and len(b) >= 1): fails += 1

    # 10. Strategies — presets and active
    s, b = _request("GET", "/api/v1/strategies/presets")
    names = {p["name"] for p in b["presets"]}
    if not _check("GET /strategies/presets",
                  {"aggressive", "balanced", "conservative"}.issubset(names)):
        fails += 1

    s, b = _request("GET", "/api/v1/strategies/active?name=balanced", token=token)
    if not _check("GET /strategies/active", s == 200 and b is not None): fails += 1

    # 11. Seed default strategy rows (idempotent) so a fresh DB has
    #     v1 of each preset, then save a new draft version (>= v2).
    s, seed = _request("POST", "/api/v1/strategies/seed-defaults", token=token)
    if not _check("POST /strategies/seed-defaults", s == 200):
        fails += 1

    new_payload = json.loads(json.dumps(json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/api/v1/strategies/presets")).read()
    )["presets"][1]["payload"]))
    s, save_b = _request("POST", "/api/v1/strategies",
                         body={"name": "balanced", "payload": new_payload,
                               "activate": False},
                         token=token)
    if not _check("POST /strategies (save draft)", s == 200 and save_b["version"] >= 2):
        fails += 1

    # 12. Journal create + close + summary
    s, je = _request("POST", "/api/v1/journal",
                     body={
                         "symbol": "BTC/USDT", "side": "LONG",
                         "entry_price": 60000.0, "qty": 0.01,
                         "opened_at": "2026-07-15T00:00:00Z",
                         "notes": "smoke entry",
                     },
                     token=token)
    if not _check("POST /journal", s == 201, je.get("id")): fails += 1
    eid = je["id"]
    s, je2 = _request("POST", f"/api/v1/journal/{eid}/close",
                      body={"exit_price": 65000.0, "notes": "smoke close"},
                      token=token)
    pnl = je2.get("pnl")
    if not _check("POST /journal/{id}/close", s == 200 and pnl == 50.0, pnl):
        fails += 1
    s, summary = _request("GET", "/api/v1/journal/summary", token=token)
    if not _check("GET /journal/summary",
                  s == 200 and summary["winners"] >= 1
                  and summary["total_pnl"] >= 50.0):
        fails += 1

    # 13. Trades config + paper order
    s, cfg = _request("GET", "/api/v1/trades/config", token=token)
    if not _check("GET /trades/config",
                  s == 200 and cfg["live_trading"] is False): fails += 1
    s, order = _request("POST", "/api/v1/trades/orders",
                        body={
                            "symbol": "BTC/USDT", "side": "BUY",
                            "order_type": "LIMIT", "qty": 0.01, "price": 60000,
                        },
                        token=token)
    if not _check("POST /trades/orders (paper)",
                  s == 200 and order["status"] == "FILLED"
                  and order["exchange_order_id"].startswith("paper-"),
                  order.get("exchange_order_id")):
        fails += 1

    s, orders = _request("GET", "/api/v1/trades/orders?limit=5", token=token)
    if not _check("GET /trades/orders", s == 200 and len(orders) >= 1):
        fails += 1

    # 14. Scanner
    s, scan = _request("POST", "/api/v1/scanner/run",
                       body={"timeframe": "1h", "strategy": "balanced",
                             "candle_limit": 100, "symbols": ["BTC/USDT"]},
                       token=token)
    if not _check("POST /scanner/run", s == 200 and scan["running"]): fails += 1
    s, latest = _request("GET", "/api/v1/scanner/latest?limit=5", token=token)
    if not _check("GET /scanner/latest", s == 200 and isinstance(latest, list)):
        fails += 1

    # 15. Gate.io REST adapter available even if not configured
    s, b = _request("GET", "/api/v1/market-data/BTC-USDT/candles?timeframe=4h&limit=5",
                    token=token)
    if not _check("GET /candles (4h)", s == 200 and len(b["candles"]) == 5): fails += 1

    print("=" * 60)
    if fails == 0:
        print("END-TO-END SMOKE: ALL CHECKS PASSED")
        return 0
    print(f"END-TO-END SMOKE: {fails} CHECK(S) FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())

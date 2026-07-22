"""End-to-end live verification harness for the ConTraCo V2 build.

  1. Hits /health.
  2. Registers a brand-new user.
  3. Logs in.
  4. Pulls symbols/venues/search from Binance.
  5. Pulls OHLCV from Binance directly via /market-data.
  6. Runs /analysis/run with the BTC/USDT candles flowing through the
     real Binance provider (no mock).
  7. Verifies agent leaderboard + journal export + risk-of-ruin.
  8. Verifies new DEX / fundamentals / macro / sentiment endpoints.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from typing import Any

BASE = "http://127.0.0.1:8766"


def req(method: str, path: str, *, token: str | None = None, body: Any | None = None) -> dict:
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return {"status": resp.status, "data": json.loads(raw) if raw else None}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        return {"status": exc.code, "data": raw}
    except urllib.error.URLError as exc:
        return {"status": 0, "data": str(exc)}


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        results.append((label, ok, detail))
        print(("PASS" if ok else "FAIL"), label, detail)

    h = req("GET", "/health")
    check("health", h["status"] == 200 and h["data"].get("market_data_provider", "").strip() == "binance",
          f"-> {h}")

    # Register + login
    creds = {"email": "v2_tester@example.com", "password": "V2Strong!Pass"}
    r = req("POST", "/api/v1/auth/register", body=creds)
    if r["status"] not in (200, 201, 400):
        check("register", False, str(r))
        return 1
    login = req("POST", "/api/v1/auth/login", body=creds)
    if login["status"] != 200:
        check("login", False, str(login))
        return 1
    token = login["data"]["access_token"]
    check("login", True, f"token=...{token[-6:]}")

    # Symbols/venues
    v = req("GET", "/api/v1/symbols/venues", token=token)
    check("symbols/venues", v["status"] == 200 and isinstance(v["data"], list) and len(v["data"]) >= 5,
          f"venues={len(v.get('data', [])) if isinstance(v.get('data'), list) else 0}")

    # Symbol search
    s = req("GET", "/api/v1/symbols/search?q=BTC", token=token)
    if s["status"] == 200:
        syms = s["data"] if isinstance(s["data"], list) else s["data"].get("results", [])
        check("symbols/search BTC", isinstance(syms, list) and len(syms) > 0,
              f"matches={len(syms) if isinstance(syms, list) else 0}")
    else:
        check("symbols/search BTC", False, str(s))

    # Get candles via market-data (against Binance)
    md = req("GET", "/api/v1/market-data/BTCUSDT/candles?timeframe=1h&limit=10", token=token)
    if md["status"] == 200:
        n = len(md["data"].get("candles", [])) if isinstance(md["data"], dict) else 0
        check("candles BTC 1h", n >= 5, f"got {n} candles")
    else:
        check("candles BTC 1h", False, str(md)[:200])

    # Analysis run (real Binance data, real LLM)
    a = req("POST", "/api/v1/analysis/run", token=token,
            body={"symbol": "BTC/USDT", "timeframe": "1h", "strategy": "balanced"})
    if a["status"] == 200:
        d = a["data"]
        run = d.get("run") or d
        fs = run.get("final_state") or (run.get("decision") or {}).get("final_state")
        check("analysis/run", True, f"final_state={fs} score={run.get('composite_score', 'n/a')}")
    else:
        check("analysis/run", False, str(a)[:300])

    # DEX network list
    dn = req("GET", "/api/v1/dex/networks")
    check("dex/networks", dn["status"] == 200 and "ethereum" in dn["data"]["networks"], str(dn))

    # DEX overview
    do = req("GET", "/api/v1/dex/overview")
    check("dex/overview", do["status"] == 200, str(do)[:200])

    # DEX tranche discovery
    tr = req("GET", "/api/v1/dex/tranches/robinhood-base")
    check("dex/tranches/robinhood-base", tr["status"] == 200, "-> " + str(tr)[:200])

    # Fundamentals snapshot (BTC/USDT, real CoinGecko + DeFiLlama + Fear&Greed)
    fs = req("GET", "/api/v1/fundamentals/free/snapshot?symbol=BTC/USDT")
    if fs["status"] == 200 and "coingecko_prices" in fs.get("data", {}):
        sub = fs["data"]["coingecko_prices"].get("prices", {})
        if "BTC/USDT" in sub:
            price = sub["BTC/USDT"]["usd"]
            check("fundamentals/snapshot", True, f"BTC USD={price}")
        else:
            check("fundamentals/snapshot", False, str(fs.get("data"))[:300])
    else:
        check("fundamentals/snapshot", False, str(fs)[:200])

    # Fear & Greed
    fg = req("GET", "/api/v1/fundamentals/free/fear-and-greed")
    check("fear-and-greed", fg["status"] == 200, f"-> {fg}")

    # Macro
    m = req("GET", "/api/v1/macro/snapshot")
    check("macro/snapshot", m["status"] == 200, f"-> {str(m)[:200]}")

    # Leaderboard
    lb = req("GET", "/api/v1/analytics/leaderboard/agents", token=token)
    check("leaderboard/agents", lb["status"] == 200, str(lb)[:200])

    # Journal export (csv)
    je = req("GET", "/api/v1/analytics/journal/export?format=json", token=token)
    check("journal/export", je["status"] == 200, str(je)[:200])

    # Risk-of-ruin
    ror = req("POST", "/api/v1/risk/risk-of-ruin", token=token,
              body={"win_rate": 0.55, "avg_win": 100, "avg_loss": 60,
                    "bankroll": 10000, "unit_size": 50})
    check("risk-of-ruin", ror["status"] == 200 and "risk_of_ruin_pct" in ror["data"], str(ror)[:200])

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{passed}/{len(results)} passed; {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Live end-to-end smoke audit. Read-only. Classifies every GET endpoint."""
import json, time, urllib.request, urllib.error

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@example.com", "password": "ChangeMe123!"}

def req(method, path, token=None, body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode()
            dt = time.time() - t0
            try:
                return resp.status, json.loads(raw), dt
            except Exception:
                return resp.status, raw, dt
    except urllib.error.HTTPError as e:
        dt = time.time() - t0
        try:
            return e.code, json.loads(e.read().decode()), dt
        except Exception:
            return e.code, e.reason, dt
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}", time.time() - t0

# login
st, tok_resp, _ = req("POST", "/api/v1/auth/login", body=ADMIN)
token = tok_resp.get("access_token") if isinstance(tok_resp, dict) else None
print(f"# LOGIN: status={st} token={'yes' if token else 'NO -> ' + str(tok_resp)}")

# (path, params-substituted) GET endpoints with realistic params
S = "BTCUSDT"
ETH_WHALE = "0x28C6c06298d514Db089934071355E5743bf21d60"  # binance hot wallet
SOL_TOK = "So11111111111111111111111111111111111111112"
GETS = [
    "/api/v1/alerts",
    "/api/v1/analysis/runs",
    "/api/v1/analytics/overview",
    "/api/v1/analytics/by-hour",
    "/api/v1/analytics/by-symbol",
    "/api/v1/analytics/equity-curve",
    "/api/v1/analytics/monthly-returns",
    "/api/v1/analytics/leaderboard/agents",
    "/api/v1/arbitrage/scan",
    "/api/v1/arbitrage/spreads",
    "/api/v1/arbitrage/yield",
    "/api/v1/auth/me",
    "/api/v1/backtest",
    "/api/v1/charting/pinescript?symbol=" + S,
    "/api/v1/charting/signals?symbol=" + S,
    "/api/v1/derivatives/funding?symbol=" + S,
    "/api/v1/derivatives/liquidation-heatmap?symbol=" + S,
    "/api/v1/derivatives/open-interest?symbol=" + S,
    "/api/v1/dex/networks",
    "/api/v1/dex/overview",
    "/api/v1/dex/pools/top?network=solana",
    "/api/v1/dex/snipe/new-pools?network=solana",
    "/api/v1/dex/snipe/trending?network=solana",
    "/api/v1/dex/tranches/leaderboard",
    "/api/v1/fundamentals/calendar",
    "/api/v1/fundamentals/context?symbol=" + S,
    "/api/v1/fundamentals/free/calendar",
    "/api/v1/fundamentals/free/defillama/top",
    "/api/v1/fundamentals/free/fear-and-greed",
    "/api/v1/fundamentals/free/snapshot?symbol=" + S,
    "/api/v1/fundamentals/funding?symbol=" + S,
    "/api/v1/fundamentals/news?symbol=" + S,
    "/api/v1/fundamentals/onchain?symbol=" + S,
    "/api/v1/intel/sentiment?symbol=" + S,
    "/api/v1/intel/token-safety?address=" + SOL_TOK + "&network=solana",
    "/api/v1/intel/trenches",
    "/api/v1/intel/whale-movements",
    "/api/v1/journal",
    "/api/v1/journal/summary",
    "/api/v1/liquidity/funding-oi?symbol=" + S,
    "/api/v1/liquidity/heatmap?symbol=" + S,
    "/api/v1/macro/snapshot",
    "/api/v1/market-data/" + S + "/candles?interval=1h&limit=50",
    "/api/v1/market-data/" + S + "/orderbook",
    "/api/v1/market-overview",
    "/api/v1/market/top",
    "/api/v1/market/tv-prefixes",
    "/api/v1/mtf/presets",
    "/api/v1/news/context?symbol=" + S,
    "/api/v1/risk/attribution",
    "/api/v1/scanner/latest",
    "/api/v1/scanner/status",
    "/api/v1/schedule/status",
    "/api/v1/sec/context?symbol=AAPL",
    "/api/v1/sec/facts?symbol=AAPL",
    "/api/v1/sec/filings?symbol=AAPL",
    "/api/v1/sentiment/" + S,
    "/api/v1/strategies",
    "/api/v1/strategies/active",
    "/api/v1/strategies/presets",
    "/api/v1/symbols",
    "/api/v1/symbols/search?q=BTC",
    "/api/v1/symbols/spot-pairs",
    "/api/v1/symbols/tv-catalog",
    "/api/v1/symbols/venues",
    "/api/v1/trades/config",
    "/api/v1/trades/orders",
    "/api/v1/wallets/" + ETH_WHALE + "/score?network=ethereum",
    "/api/v1/wallets/" + ETH_WHALE + "/tokens?network=ethereum",
    "/api/v1/council/wallets/" + ETH_WHALE + "/analyze?network=ethereum",
]

def classify(status, body, dt):
    if status == -1:
        return "CONNERR"
    if status >= 500:
        return "5xx"
    if status == 404:
        return "404"
    if status in (401, 403):
        return "AUTH"
    if status >= 400:
        return "4xx"
    # 2xx: check emptiness
    empty = False
    if isinstance(body, list):
        empty = len(body) == 0
    elif isinstance(body, dict):
        # common empty shapes
        for k in ("items", "data", "results", "rows", "entries", "signals", "pools", "candles"):
            if k in body and isinstance(body[k], list) and len(body[k]) == 0:
                empty = True
        if not body:
            empty = True
    tag = "OK"
    if empty:
        tag = "EMPTY"
    if dt > 8:
        tag += "/SLOW"
    return tag

results = []
for path in GETS:
    st, body, dt = req("GET", path, token=token)
    tag = classify(st, body, dt)
    note = ""
    if tag not in ("OK",) and not tag.startswith("OK"):
        # capture a short error/detail snippet
        if isinstance(body, dict):
            note = str(body.get("detail") or body.get("error") or body.get("message") or "")[:120]
        else:
            note = str(body)[:120]
    results.append((tag, st, f"{dt:.1f}s", path, note))
    print(f"{tag.ljust(10)} {str(st).ljust(4)} {dt:5.1f}s {path}  {note}")

print("\n# ---- SUMMARY ----")
from collections import Counter
c = Counter(r[0].split('/')[0] for r in results)
print(dict(c))
print("\n# PROBLEMS:")
for tag, st, dt, path, note in results:
    base = tag.split('/')[0]
    if base not in ("OK",):
        print(f"  {tag.ljust(10)} {path}  [{st}] {note}")

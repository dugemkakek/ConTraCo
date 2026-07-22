"""Quick connectivity probe."""
import httpx

r = httpx.get(
    "https://api.binance.com/api/v3/klines",
    params={"symbol": "BTCUSDT", "interval": "1h", "limit": 5},
    verify=False,
    timeout=10,
    headers={"User-Agent": "confluence-trading-consultant/1.0"},
)
print(f"status: {r.status_code}")
print(f"body[:500]: {r.text[:500]}")

r2 = httpx.get(
    "https://data-api.binance.vision/api/v3/klines",
    params={"symbol": "BTCUSDT", "interval": "1h", "limit": 5},
    verify=False,
    timeout=10,
    headers={"User-Agent": "confluence-trading-consultant/1.0"},
)
print(f"vision status: {r2.status_code}")
print(f"vision body[:500]: {r2.text[:500]}")

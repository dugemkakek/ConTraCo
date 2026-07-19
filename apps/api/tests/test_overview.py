import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_market_overview_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        # register to get a token
        import random
        email = f"ov-{random.randint(10000,99999)}@example.com"
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "VeryStrong1!"},
        )
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]

        r = await client.get(
            "/api/v1/market-overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()

    assert data["provider"] in ("mock", "gateio")
    assert isinstance(data["as_of"], str)
    assert len(data["tickers"]) >= 3

    btc = next(t for t in data["tickers"] if t["symbol"] == "BTC/USDT")
    assert btc["last"] > 0
    assert btc["change_24h_pct"] is not None
    assert btc["sparkline"]  # non-empty list
    assert btc["rsi_14"] is None or 0 <= btc["rsi_14"] <= 100
    assert btc["trend"] in ("up", "down", "flat")

    b = data["breadth"]
    assert b["up"] + b["down"] + b["flat"] == len(data["tickers"])

    m = data["movers"]
    assert len(m["gainers"]) >= 1
    assert len(m["losers"]) >= 1

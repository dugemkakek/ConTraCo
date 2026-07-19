import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "redis_mode" in body
    assert "market_data_provider" in body


@pytest.mark.asyncio
async def test_get_candles_btc_1h():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/market-data/BTC-USDT/candles", params={"timeframe": "1h", "limit": 50}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTC/USDT"
    assert len(body["candles"]) == 50
    assert body["data_freshness"] in {"FRESH", "STALE", "UNKNOWN"}
    timestamps = [c["timestamp"] for c in body["candles"]]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_unsupported_symbol_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/market-data/DOGE-USDT/candles")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unsupported_timeframe_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/market-data/BTC-USDT/candles", params={"timeframe": "3m"}
        )
    assert resp.status_code == 400

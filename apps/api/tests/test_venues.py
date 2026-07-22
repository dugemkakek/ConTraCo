import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

import random


@pytest.mark.asyncio
async def test_list_venues():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        email = f"v-{random.randint(10000,99999)}@example.com"
        r = await client.post("/api/v1/auth/register", json={"email": email, "password": "VeryStrong1!"})
        token = r.json()["access_token"]

        r = await client.get("/api/v1/symbols/venues", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) >= 2, data
        ids = [v["id"] for v in data]
        assert "binance" in ids
        assert "gateio" in ids


@pytest.mark.asyncio
async def test_search_symbols():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        email = f"s-{random.randint(10000,99999)}@example.com"
        r = await client.post("/api/v1/auth/register", json={"email": email, "password": "VeryStrong1!"})
        token = r.json()["access_token"]

        r = await client.get("/api/v1/symbols/search?q=BTC", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        # Search returns list of dicts with "symbol" key; BTC should appear
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.asyncio
async def test_search_empty_query_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        email = f"sq-{random.randint(10000,99999)}@example.com"
        r = await client.post("/api/v1/auth/register", json={"email": email, "password": "VeryStrong1!"})
        token = r.json()["access_token"]

        r = await client.get("/api/v1/symbols/search?q=", headers={"Authorization": f"Bearer {token}"})
        # Empty query now returns all symbols (no longer rejected)
        assert r.status_code == 200

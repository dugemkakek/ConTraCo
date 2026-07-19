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
        assert "mock" in ids
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
        assert any("BTC/USDT" in s["symbol"] for s in data), data


@pytest.mark.asyncio
async def test_search_empty_query_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        email = f"sq-{random.randint(10000,99999)}@example.com"
        r = await client.post("/api/v1/auth/register", json={"email": email, "password": "VeryStrong1!"})
        token = r.json()["access_token"]

        r = await client.get("/api/v1/symbols/search?q=", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422  # validation error

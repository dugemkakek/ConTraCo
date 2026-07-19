"""End-to-end API integration tests."""

from __future__ import annotations

import pytest

from app.db.models import AnalysisRun, FinalState, User
from app.security import hash_password


@pytest.mark.asyncio
async def test_register_login_me(client, db_session):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "VeryStrong1!"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    token = body["access_token"]
    r2 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "VeryStrong1!"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "WrongPassword1!"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_run_analysis_creates_persisted_run(client, db_session):
    # Seed a user directly
    user = User(
        email="carol@example.com", password_hash=hash_password("VeryStrong1!"),
        is_active=True, is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "VeryStrong1!"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Run an analysis
    r = await client.post(
        "/api/v1/analysis/run",
        json={"symbol": "BTC/USDT", "timeframe": "1h", "strategy": "balanced"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "BTC/USDT"
    assert body["status"] in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}
    assert body["final_state"] in {s.value for s in FinalState}
    assert len(body["gates"]) == 9
    assert len(body["opinions"]) == 6
    assert body["decision"] is not None

    # The run is queryable by id
    r2 = await client.get(f"/api/v1/analysis/runs/{body['id']}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_runs_listing(client, db_session):
    user = User(
        email="dave@example.com", password_hash=hash_password("VeryStrong1!"),
        is_active=True,
    )
    db_session.add(user); db_session.commit(); db_session.refresh(user)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "VeryStrong1!"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for sym in ("BTC/USDT", "ETH/USDT"):
        await client.post(
            "/api/v1/analysis/run",
            json={"symbol": sym, "timeframe": "1h"}, headers=headers,
        )
    r2 = await client.get("/api/v1/analysis/runs", headers=headers)
    assert r2.status_code == 200
    assert len(r2.json()) >= 2


@pytest.mark.asyncio
async def test_strategy_presets_and_save(client, db_session):
    user = User(
        email="eve@example.com", password_hash=hash_password("VeryStrong1!"),
        is_active=True,
    )
    db_session.add(user); db_session.commit(); db_session.refresh(user)
    headers = {"Authorization": f"Bearer {(await client.post('/api/v1/auth/login', json={'email': 'eve@example.com', 'password': 'VeryStrong1!'})).json()['access_token']}"}
    r = await client.get("/api/v1/strategies/presets")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["presets"]}
    assert {"aggressive", "balanced", "conservative"} <= names


@pytest.mark.asyncio
async def test_journal_create_list_close(client, db_session):
    user = User(
        email="frank@example.com", password_hash=hash_password("VeryStrong1!"),
        is_active=True,
    )
    db_session.add(user); db_session.commit(); db_session.refresh(user)
    headers = {"Authorization": f"Bearer {(await client.post('/api/v1/auth/login', json={'email': 'frank@example.com', 'password': 'VeryStrong1!'})).json()['access_token']}"}

    r = await client.post(
        "/api/v1/journal",
        json={
            "symbol": "BTC/USDT", "side": "LONG",
            "entry_price": 60000.0, "qty": 0.01,
            "opened_at": "2026-07-15T00:00:00Z", "notes": "manual test",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert r.json()["pnl"] is None

    r = await client.post(f"/api/v1/journal/{eid}/close",
                          json={"exit_price": 65000.0}, headers=headers)
    assert r.status_code == 200
    assert r.json()["pnl"] == pytest.approx(50.0)

    r = await client.get("/api/v1/journal/summary", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["winners"] == 1


@pytest.mark.asyncio
async def test_trade_paper_execution(client, db_session):
    user = User(
        email="grace@example.com", password_hash=hash_password("VeryStrong1!"),
        is_active=True,
    )
    db_session.add(user); db_session.commit(); db_session.refresh(user)
    headers = {"Authorization": f"Bearer {(await client.post('/api/v1/auth/login', json={'email': 'grace@example.com', 'password': 'VeryStrong1!'})).json()['access_token']}"}

    r = await client.get("/api/v1/trades/config", headers=headers)
    assert r.status_code == 200
    assert r.json()["live_trading"] is False

    r = await client.post(
        "/api/v1/trades/orders",
        json={
            "symbol": "BTC/USDT", "side": "BUY", "order_type": "LIMIT",
            "qty": 0.01, "price": 60000.0,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "FILLED"
    assert body["exchange_order_id"].startswith("paper-")

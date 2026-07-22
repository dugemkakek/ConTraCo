"""Tests for risk engine, scheduling, backtest API, and P&L attribution."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.engine.risk.risk_of_ruin import calculate_risk_of_ruin, calculate_portfolio_exposure
from app.engine.scheduling import active_sessions, is_killzone, next_session_open, session_status


# ── Risk of Ruin ──

class TestRiskOfRuin:
    def test_positive_edge(self):
        r = calculate_risk_of_ruin(win_rate=0.55, avg_win=200, avg_loss=100, bankroll=10000, unit_size=100)
        assert r.risk_of_ruin_pct < 50
        assert r.edge > 0

    def test_no_edge(self):
        r = calculate_risk_of_ruin(win_rate=0.30, avg_win=100, avg_loss=200, bankroll=10000, unit_size=100)
        assert r.risk_of_ruin_pct == 100.0
        assert r.edge <= 0

    def test_zero_inputs(self):
        r = calculate_risk_of_ruin(win_rate=0.5, avg_win=0, avg_loss=100, bankroll=10000, unit_size=100)
        assert r.risk_of_ruin_pct == 100.0

    def test_high_edge_low_ruin(self):
        r = calculate_risk_of_ruin(win_rate=0.70, avg_win=300, avg_loss=100, bankroll=50000, unit_size=100)
        assert r.risk_of_ruin_pct < 1.0


# ── Portfolio Exposure ──

class TestPortfolioExposure:
    def test_basic(self):
        positions = [
            {"symbol": "BTC", "side": "LONG", "qty": 0.1, "entry_price": 60000},
            {"symbol": "ETH", "side": "SHORT", "qty": 2.0, "entry_price": 3000},
        ]
        r = calculate_portfolio_exposure(positions, equity=20000, cap_pct=80)
        assert r.total_notional == 12000  # 6000 + 6000
        assert r.total_pct == 60.0
        assert not r.breached
        assert r.long_pct == 30.0
        assert r.short_pct == 30.0
        assert r.net_pct == 0.0

    def test_breach(self):
        positions = [{"symbol": "BTC", "side": "LONG", "notional": 15000}]
        r = calculate_portfolio_exposure(positions, equity=10000, cap_pct=100)
        assert r.breached
        assert r.total_pct == 150.0

    def test_zero_equity(self):
        r = calculate_portfolio_exposure([], equity=0)
        assert r.breached

    def test_notional_field(self):
        positions = [{"symbol": "SOL", "side": "LONG", "notional": 500}]
        r = calculate_portfolio_exposure(positions, equity=10000)
        assert r.total_notional == 500
        assert r.positions[0].pct_of_equity == 5.0


# ── Scheduling ──

class TestScheduling:
    def test_london_session(self):
        dt = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
        sessions = active_sessions(dt)
        assert "london" in sessions
        assert "new_york" not in sessions

    def test_ny_session(self):
        dt = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
        sessions = active_sessions(dt)
        assert "new_york" in sessions
        assert "london" in sessions
        assert "london_ny_overlap" in sessions

    def test_sydney_wraps_midnight(self):
        dt = datetime(2026, 7, 22, 23, 0, tzinfo=timezone.utc)
        sessions = active_sessions(dt)
        assert "sydney" in sessions

    def test_dead_zone(self):
        # 06:30 UTC — tokyo ended at 09:00, sydney ended at 06:00, london starts 07:00
        dt = datetime(2026, 7, 22, 6, 30, tzinfo=timezone.utc)
        sessions = active_sessions(dt)
        assert "sydney" not in sessions
        assert "london" not in sessions

    def test_is_killzone(self):
        dt = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
        assert is_killzone(dt)

    def test_next_session(self):
        dt = datetime(2026, 7, 22, 6, 30, tzinfo=timezone.utc)
        name, mins = next_session_open(dt)
        assert name == "london"
        assert mins == 30.0

    def test_session_status_shape(self):
        s = session_status()
        assert "active_sessions" in s
        assert "is_killzone" in s
        assert "next_session" in s
        assert "sessions" in s
        assert len(s["sessions"]) == 4


# ── API endpoint tests ──

@pytest.mark.asyncio
async def test_schedule_status_endpoint(client):
    r = await client.get("/api/v1/schedule/status")
    assert r.status_code == 200
    body = r.json()
    assert "active_sessions" in body
    assert "sessions" in body


@pytest.mark.asyncio
async def test_risk_of_ruin_endpoint(client):
    r = await client.post("/api/v1/risk/risk-of-ruin", json={
        "win_rate": 0.55, "avg_win": 200, "avg_loss": 100,
        "bankroll": 10000, "unit_size": 100,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["edge"] > 0
    assert body["risk_of_ruin_pct"] < 100


@pytest.mark.asyncio
async def test_exposure_endpoint(client):
    r = await client.post("/api/v1/risk/exposure", json={
        "positions": [
            {"symbol": "BTC", "side": "LONG", "qty": 0.1, "entry_price": 60000},
        ],
        "equity": 20000,
        "cap_pct": 80,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total_pct"] == 30.0
    assert not body["breached"]


@pytest.mark.asyncio
async def test_backtest_requires_auth(client):
    r = await client.get("/api/v1/backtest")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_backtest_list_empty(client):
    # Register + get token
    await client.post("/api/v1/auth/register", json={
        "email": "bt@test.com", "password": "Str0ng!Pass",
    })
    r = await client.post("/api/v1/auth/login", json={
        "email": "bt@test.com", "password": "Str0ng!Pass",
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r2 = await client.get("/api/v1/backtest", headers=headers)
    assert r2.status_code == 200
    assert r2.json() == []


@pytest.mark.asyncio
async def test_backtest_run_insufficient_candles(client):
    await client.post("/api/v1/auth/register", json={
        "email": "bt2@test.com", "password": "Str0ng!Pass",
    })
    r = await client.post("/api/v1/auth/login", json={
        "email": "bt2@test.com", "password": "Str0ng!Pass",
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r2 = await client.post("/api/v1/backtest/run", json={
        "symbol": "BTC",
        "timeframe": "1h",
        "start_date": "2026-01-01T00:00:00Z",
        "end_date": "2026-01-02T00:00:00Z",
    }, headers=headers)
    assert r2.status_code == 400
    assert "insufficient" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_attribution_empty(client):
    await client.post("/api/v1/auth/register", json={
        "email": "attr@test.com", "password": "Str0ng!Pass",
    })
    r = await client.post("/api/v1/auth/login", json={
        "email": "attr@test.com", "password": "Str0ng!Pass",
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r2 = await client.get("/api/v1/risk/attribution", headers=headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["total_closed_trades"] == 0
    assert body["gates"] == []

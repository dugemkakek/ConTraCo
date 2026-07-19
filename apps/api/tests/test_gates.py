"""Unit tests for the 6 deterministic gates."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import GateStatus
from app.engine.gates import ALL_GATES, GateContext
from app.schemas.candle import Candle


def _make_candles(n: int, *, start_price: float = 100.0, seed: int = 1, drift: float = 0.0):
    rng = random.Random(seed)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = start_price
    for i in range(n):
        # Add a controllable drift on top of noise.
        price *= 1 + drift + (rng.random() - 0.5) * 0.02
        candles.append(
            Candle(
                timestamp=base + timedelta(hours=i),
                open=price * 0.999,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000.0,
            )
        )
    return candles


async def _run(gate, ctx):
    return await gate.evaluate(ctx)


@pytest.mark.asyncio
async def test_market_regime_bullish_strong_trend():
    candles = _make_candles(250, drift=0.005)  # persistent uptrend
    g = next(x for x in ALL_GATES if x.name == "market_regime")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles))
    assert ev.status in {GateStatus.PASS, GateStatus.FAIL, GateStatus.NEUTRAL}
    assert ev.score > 0  # drift was positive
    assert 0.0 <= ev.confidence <= 1.0
    assert "adx" in ev.evidence


@pytest.mark.asyncio
async def test_market_regime_insufficient_history():
    candles = _make_candles(20)
    g = next(x for x in ALL_GATES if x.name == "market_regime")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles))
    assert ev.status == GateStatus.UNAVAILABLE
    assert ev.confidence == 0.0


@pytest.mark.asyncio
async def test_classical_ta_outputs_sub_signals():
    candles = _make_candles(200, drift=0.002)
    g = next(x for x in ALL_GATES if x.name == "classical_ta")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles))
    assert ev.status in {GateStatus.PASS, GateStatus.FAIL, GateStatus.NEUTRAL}
    assert "rsi14" in ev.evidence
    assert "macd_hist" in ev.evidence
    assert "bollinger_pct_b" in ev.evidence


@pytest.mark.asyncio
async def test_market_structure_swing_counts():
    candles = _make_candles(100, start_price=100.0, seed=3)
    g = next(x for x in ALL_GATES if x.name == "market_structure")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles))
    assert "swing_highs" in ev.evidence
    assert "swing_lows" in ev.evidence
    assert ev.status in {GateStatus.PASS, GateStatus.FAIL, GateStatus.NEUTRAL}


@pytest.mark.asyncio
async def test_volume_momentum_sub_signals():
    candles = _make_candles(200, drift=0.003)
    g = next(x for x in ALL_GATES if x.name == "volume_momentum")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles))
    assert "vol_ratio_5vs20" in ev.evidence
    assert "obv_slope_per_20" in ev.evidence
    assert ev.confidence > 0


@pytest.mark.asyncio
async def test_fundamental_context_no_order_book():
    candles = _make_candles(100)
    g = next(x for x in ALL_GATES if x.name == "fundamental_context")
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles, order_book=None))
    assert ev.status == GateStatus.NEUTRAL
    assert ev.confidence < 0.5


@pytest.mark.asyncio
async def test_fundamental_context_balanced_book():
    candles = _make_candles(100)
    g = next(x for x in ALL_GATES if x.name == "fundamental_context")
    ob = {
        "bids": [[100.0 - 0.01 * i, 1.0] for i in range(20)],
        "asks": [[100.0 + 0.01 * i, 1.0] for i in range(20)],
    }
    ev = await _run(g, GateContext("BTC/USDT", "1h", candles, order_book=ob))
    assert "imbalance" in ev.evidence
    assert ev.status in {GateStatus.PASS, GateStatus.FAIL, GateStatus.NEUTRAL}


@pytest.mark.asyncio
async def test_risk_tradeability_pass_for_healthy_symbol():
    g = next(x for x in ALL_GATES if x.name == "risk_tradeability")
    ev = await _run(
        g,
        GateContext(
            "BTC/USDT",
            "1h",
            _make_candles(100),
            order_book={"bids": [[100, 5]], "asks": [[100.05, 4]]},
            symbol_meta={"is_active": True, "quote_volume_24h": 5_000_000},
        ),
    )
    assert ev.status == GateStatus.PASS
    assert ev.confidence == 1.0


@pytest.mark.asyncio
async def test_risk_tradeability_veto_low_liquidity():
    g = next(x for x in ALL_GATES if x.name == "risk_tradeability")
    ev = await _run(
        g,
        GateContext(
            "X/USDT",
            "1h",
            _make_candles(100),
            symbol_meta={"is_active": True, "quote_volume_24h": 100},
        ),
    )
    assert ev.status == GateStatus.VETO
    assert "volume" in ev.reason.lower() or "liquidity" in ev.reason.lower()


@pytest.mark.asyncio
async def test_risk_tradeability_veto_wide_spread():
    g = next(x for x in ALL_GATES if x.name == "risk_tradeability")
    ev = await _run(
        g,
        GateContext(
            "BTC/USDT",
            "1h",
            _make_candles(100),
            order_book={"bids": [[100.0, 1.0]], "asks": [[110.0, 1.0]]},
            symbol_meta={"is_active": True, "quote_volume_24h": 5_000_000},
        ),
    )
    assert ev.status == GateStatus.VETO
    assert "spread" in ev.reason.lower()

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import pytest

from app.schemas.candle import Candle
from app.services.market_data.snapshot import (
    MarketSnapshotPipeline,
    RateLimitBudget,
    RateLimitExceeded,
    SnapshotCache,
)


class MemoryCache:
    def __init__(self):
        self.values: dict[str, str] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, _seconds: int, value: str):
        self.values[key] = value
        return True


class Provider:
    venue_id = "test"
    venue_label = "Test"

    def __init__(self, name: str, *, fail: bool = False):
        self.name = name
        self.fail = fail
        self.calls = 0

    def is_symbol_supported(self, _symbol: str):
        return True

    def is_timeframe_supported(self, _timeframe: str):
        return True

    def supported_symbols(self):
        return ["BTC/USDT"]

    def supported_timeframes(self):
        return ["1h"]

    async def get_ohlcv(self, _symbol: str, _timeframe: str, limit: int = 300):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return [Candle(timestamp=datetime.now(timezone.utc), open=1, high=2, low=.5, close=1.5, volume=10)][:limit]


@pytest.mark.asyncio
async def test_snapshot_cache_prevents_duplicate_provider_call():
    provider = Provider("primary")
    pipeline = MarketSnapshotPipeline([provider], SnapshotCache(MemoryCache()))

    first = await pipeline.build("BTC/USDT", "1h", categories=("ohlcv",))
    second = await pipeline.build("BTC/USDT", "1h", categories=("ohlcv",))

    assert provider.calls == 1
    assert first.candles[0].close == second.candles[0].close == 1.5
    assert second.provenance["ohlcv"].provider == "primary"


@pytest.mark.asyncio
async def test_snapshot_fails_over_without_synthetic_data():
    primary = Provider("primary", fail=True)
    secondary = Provider("secondary")
    pipeline = MarketSnapshotPipeline([primary, secondary], SnapshotCache(MemoryCache()))

    snapshot = await pipeline.build("BTC/USDT", "1h", categories=("ohlcv",))

    assert primary.calls == 1
    assert secondary.calls == 1
    assert snapshot.candles[0].close == 1.5
    assert snapshot.provenance["ohlcv"].provider == "secondary"
    assert snapshot.provenance["ohlcv"].failover_from == "primary"


@pytest.mark.asyncio
async def test_snapshot_uses_explicitly_stale_cache_after_all_failures():
    client = MemoryCache()
    cache = SnapshotCache(client)
    provider = Provider("primary", fail=True)
    key = cache._key("ohlcv", "primary", "BTC/USDT", "1h:300")
    candle = Candle(timestamp=datetime.now(timezone.utc), open=1, high=2, low=.5, close=1.25, volume=4)
    client.values[key] = json.dumps({
        "fetched_at_epoch": time.time() - 120,
        "fresh_until_epoch": time.time() - 60,
        "value": [candle.model_dump(mode="json")],
    })

    snapshot = await MarketSnapshotPipeline([provider], cache).build(
        "BTC/USDT", "1h", categories=("ohlcv",)
    )

    assert snapshot.candles[0].close == 1.25
    assert snapshot.provenance["ohlcv"].is_stale is True
    assert snapshot.stale_categories == ["ohlcv"]
    assert "stale cache" in snapshot.errors["ohlcv"]


@pytest.mark.asyncio
async def test_rate_limit_budget_rejects_without_waiting():
    budget = RateLimitBudget(capacity=1, refill_per_second=.01)
    await budget.acquire()
    with pytest.raises(RateLimitExceeded):
        await budget.acquire(wait=False)

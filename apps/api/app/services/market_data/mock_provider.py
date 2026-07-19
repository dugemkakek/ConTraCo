"""Deterministic OHLCV provider for CI, tests, and offline demos."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

SUPPORTED_SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
SUPPORTED_TIMEFRAMES = tuple(TIMEFRAME_MINUTES.keys())


class MockMarketDataProvider:
    """Seeded sine-wave + noise generator; same symbol/timeframe always
    returns the same series, so tests are deterministic."""

    name = "mock"
    venue_id = "mock"
    venue_label = "Mock"

    def __init__(self, seed: int = 42):
        self._seed = seed

    def is_symbol_supported(self, symbol: str) -> bool:
        return symbol.upper() in SUPPORTED_SYMBOLS

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in TIMEFRAME_MINUTES

    def supported_symbols(self) -> list[str]:
        return list(SUPPORTED_SYMBOLS)

    def supported_timeframes(self) -> list[str]:
        return list(SUPPORTED_TIMEFRAMES)

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300,
    ) -> list[Candle]:
        if not self.is_symbol_supported(symbol):
            raise ValueError(f"Unsupported symbol: {symbol}")
        if not self.is_timeframe_supported(timeframe):
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        rng = random.Random(f"{self._seed}-{symbol}-{timeframe}")
        step = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

        base_price = {
            "BTC/USDT": 65000.0,
            "ETH/USDT": 3200.0,
            "SOL/USDT": 150.0,
        }.get(symbol.upper(), 100.0)

        candles: list[Candle] = []
        price = base_price
        start = now - step * limit

        for i in range(limit):
            ts = start + step * i
            drift = math.sin(i / 15.0) * base_price * 0.01
            noise = rng.uniform(-1, 1) * base_price * 0.003
            open_ = price
            close = max(0.01, base_price + drift + noise)
            high = max(open_, close) + abs(rng.uniform(0, base_price * 0.001))
            low = min(open_, close) - abs(rng.uniform(0, base_price * 0.001))
            volume = abs(rng.uniform(50, 500)) * (1 + abs(math.sin(i / 10.0)))
            candles.append(
                Candle(
                    timestamp=ts,
                    open=round(open_, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=round(volume, 2),
                )
            )
            price = close

        return candles


def is_market_data_provider(obj: object) -> bool:
    return isinstance(obj, MarketDataProvider)

"""Market data provider interface.

A provider supplies OHLCV candles for symbols/timeframes and announces
its supported universe. Concrete implementations include the in-process
deterministic Mock (CI/demos) and a real REST+WebSocket adapter for
Gate.io spot markets.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.candle import Candle


@runtime_checkable
class MarketDataProvider(Protocol):
    """Anything that can serve OHLCV candles for the terminal."""

    name: str
    venue_id: str = ""
    venue_label: str = ""

    def is_symbol_supported(self, symbol: str) -> bool: ...

    def is_timeframe_supported(self, timeframe: str) -> bool: ...

    def supported_symbols(self) -> list[str]: ...

    def supported_timeframes(self) -> list[str]: ...

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300,
    ) -> list[Candle]: ...


__all__ = ["MarketDataProvider"]

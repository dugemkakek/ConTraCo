"""Gate.io spot REST adapter.

The terminal uses the slash-notation universe ``BTC/USDT``; Gate.io's
public REST endpoints use the underscore-notation pair ``BTC_USDT`` and
return candlesticks as ``[time_seconds, quote_volume, close, high, low,
open, base_volume]``. This module is the only place that knows about
those details — the rest of the app keeps the slash notation it had
during the Mock-only scaffold.

Docs: https://www.gate.io/docs/developers/apiv4/en/#market-candlesticks
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

GATEIO_REST_BASE = "https://api.gateio.ws/api/v4"

# Map terminal timeframes (slash notation) to Gate.io `interval` query values.
GATEIO_INTERVALS: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Curated default universe (Gate.io has hundreds of long-tail pairs;
# we whitelist liquid USDT-quoted spot pairs).
DEFAULT_UNIVERSE: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "DOT/USDT",
    "MATIC/USDT",
    "TRX/USDT",
)


def to_gateio_pair(symbol: str) -> str:
    """``BTC/USDT`` -> ``BTC_USDT``."""
    return symbol.replace("/", "_").upper()


def from_gateio_pair(pair: str) -> str:
    """``BTC_USDT`` -> ``BTC/USDT``."""
    return pair.replace("_", "/").upper()


class GateioRestProvider:
    """Gate.io REST provider — OHLCV + symbol listing."""

    name = "gateio"
    venue_id = "gateio"
    venue_label = "Gate.io"

    def __init__(
        self,
        base_url: str = GATEIO_REST_BASE,
        universe: tuple[str, ...] = DEFAULT_UNIVERSE,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        self._base_url = base_url.rstrip("/")
        self._universe = tuple(s.upper() for s in universe)
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"User-Agent": "confluence-trading-consultant/0.2"},
            )
        return self._client

    def is_symbol_supported(self, symbol: str) -> bool:
        return symbol.upper() in self._universe

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in GATEIO_INTERVALS

    def supported_symbols(self) -> list[str]:
        return list(self._universe)

    def supported_timeframes(self) -> list[str]:
        return list(GATEIO_INTERVALS.keys())

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300,
    ) -> list[Candle]:
        normalized = symbol.upper()
        if not self.is_symbol_supported(normalized):
            raise ValueError(f"Unsupported symbol: {symbol}")
        if not self.is_timeframe_supported(timeframe):
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        pair = to_gateio_pair(normalized)
        client = await self._get_client()
        params = {"currency_pair": pair, "interval": timeframe, "limit": limit}

        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.get("/spot/candlesticks", params=params)
                resp.raise_for_status()
                rows = resp.json()
                break
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                logger.warning(
                    "gate.io fetch attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )
                if attempt == self._max_retries:
                    raise
                await asyncio.sleep(2**attempt)

        candles: list[Candle] = []
        for raw in reversed(rows):
            try:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(int(raw[0]), tz=timezone.utc),
                    open=float(raw[5]),
                    high=float(raw[3]),
                    low=float(raw[4]),
                    close=float(raw[2]),
                    volume=float(raw[6]),
                ))
            except (IndexError, ValueError, TypeError) as exc:
                logger.debug("skipping malformed row: %s — %s", raw, exc)
        return candles

    async def list_spot_pairs(self) -> list[dict[str, Any]]:
        """Fetch tradable spot pairs from Gate.io."""
        client = await self._get_client()
        resp = await client.get("/spot/currency_pairs")
        resp.raise_for_status()
        return resp.json()

    async def get_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any] | None:
        """Fetch order book depth from Gate.io."""
        pair = to_gateio_pair(symbol)
        client = await self._get_client()
        try:
            resp = await client.get("/spot/order_book", params={"currency_pair": pair, "limit": str(depth)})
            if resp.status_code == 200:
                return resp.json()
        except Exception:  # noqa: BLE001
            pass
        return None


__all__ = [
    "GateioRestProvider",
    "GATEIO_REST_BASE",
    "GATEIO_INTERVALS",
    "DEFAULT_UNIVERSE",
    "to_gateio_pair",
    "from_gateio_pair",
]

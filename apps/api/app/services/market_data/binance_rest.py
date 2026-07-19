"""Binance REST adapter — OHLCV + full pair listing + TV prefix."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

BINANCE_REST_BASE = "https://api.binance.com/api/v3"

TV_PREFIX = "BINANCE"

BINANCE_INTERVALS: dict[str, str] = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}


def to_binance_pair(symbol: str) -> str:
    return symbol.replace("/", "").upper()


class BinanceRestProvider:
    name = "binance"
    venue_id = "binance"
    venue_label = "Binance"

    def __init__(self, timeout: float = 10.0):
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._pairs_cache: list[dict] | None = None
        self._cache_ts: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BINANCE_REST_BASE,
                timeout=self._timeout,
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._client

    def is_symbol_supported(self, symbol: str) -> bool:
        return True

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in BINANCE_INTERVALS

    def supported_symbols(self) -> list[str]:
        return []

    def supported_timeframes(self) -> list[str]:
        return list(BINANCE_INTERVALS.keys())

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        client = await self._get_client()
        pair = to_binance_pair(symbol)
        interval = BINANCE_INTERVALS.get(timeframe, "1h")
        resp = await client.get(
            "/klines",
            params={"symbol": pair, "interval": interval, "limit": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()
        candles: list[Candle] = []
        for raw in data:
            try:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(raw[0] / 1000, tz=timezone.utc),
                    open=float(raw[1]), high=float(raw[2]),
                    low=float(raw[3]), close=float(raw[4]), volume=float(raw[5]),
                ))
            except (IndexError, ValueError):
                continue
        return candles

    async def get_all_spot_pairs(self) -> list[dict]:
        import time
        now = time.time()
        if self._pairs_cache and (now - self._cache_ts) < 3600:
            return self._pairs_cache

        client = await self._get_client()
        resp = await client.get("/ticker/24hr")
        resp.raise_for_status()
        data = resp.json()
        pairs = []
        for t in data:
            sym = t.get("symbol", "")
            if sym.endswith("USDT"):
                pairs.append({
                    "id": sym,
                    "base": sym.replace("USDT", ""),
                    "quote": "USDT",
                    "venue": "binance",
                    "display": f"{sym.replace('USDT', '')}/USDT",
                    "volume_24h_quote": float(t.get("quoteVolume", 0)),
                    "price": float(t.get("lastPrice", 0)),
                    "change_24h_pct": float(t.get("priceChangePercent", 0)),
                    "tick_size": None,
                    "min_qty": None,
                })
        pairs.sort(key=lambda x: -x["volume_24h_quote"])
        self._pairs_cache = pairs
        self._cache_ts = now
        return pairs

    async def search_pairs(self, query: str, limit: int = 50) -> list[dict]:
        pairs = await self.get_all_spot_pairs()
        q = query.lower()
        matched = [p for p in pairs if q in p["base"].lower() or q in p["id"].lower()]
        return matched[:limit]


__all__ = ["BinanceRestProvider", "BINANCE_REST_BASE", "BINANCE_INTERVALS", "TV_PREFIX", "to_binance_pair"]

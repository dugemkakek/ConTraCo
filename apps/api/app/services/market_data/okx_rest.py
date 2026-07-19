"""OKX REST adapter — OHLCV + full pair listing + TV prefix."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

OKX_REST_BASE = "https://www.okx.com/api/v5"

TV_PREFIX = "OKX"

OKX_INTERVALS: dict[str, str] = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W",
}


def to_okx_pair(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


def from_okx_pair(pair: str) -> str:
    return pair.replace("-", "/")


class OkxRestProvider:
    name = "okx"
    venue_id = "okx"
    venue_label = "OKX"

    def __init__(self, timeout: float = 10.0):
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._pairs_cache: list[dict] | None = None
        self._cache_ts: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=OKX_REST_BASE,
                timeout=self._timeout,
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._client

    def is_symbol_supported(self, symbol: str) -> bool:
        return True  # OKX has thousands

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in OKX_INTERVALS

    def supported_symbols(self) -> list[str]:
        return []

    def supported_timeframes(self) -> list[str]:
        return list(OKX_INTERVALS.keys())

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        client = await self._get_client()
        pair = to_okx_pair(symbol)
        interval = OKX_INTERVALS.get(timeframe, "1H")
        resp = await client.get(
            "/market/candles",
            params={"instId": pair, "bar": interval, "limit": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise ValueError(f"OKX API error: {data}")
        candles: list[Candle] = []
        for raw in reversed(data.get("data", [])):
            try:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(int(raw[0]) / 1000, tz=timezone.utc),
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
        resp = await client.get("/market/tickers", params={"instType": "SPOT"})
        resp.raise_for_status()
        data = resp.json()
        pairs = []
        for t in data.get("data", []):
            inst = t.get("instId", "")
            if inst.endswith("-USDT"):
                pairs.append({
                    "id": inst,
                    "base": inst.replace("-USDT", ""),
                    "quote": "USDT",
                    "venue": "okx",
                    "display": inst.replace("-", "/"),
                    "volume_24h_quote": float(t.get("volCcy24h", 0)),
                    "price": float(t.get("last", 0)),
                    "change_24h_pct": float(t.get("change24h", 0)) * 100 if t.get("change24h") else None,
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


__all__ = ["OkxRestProvider", "OKX_REST_BASE", "OKX_INTERVALS", "TV_PREFIX", "to_okx_pair", "from_okx_pair"]

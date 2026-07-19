"""Bybit REST adapter — OHLCV + full pair listing + TV prefix."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

BYBIT_REST_BASE = "https://api.bybit.com/v5"

TV_PREFIX = "BYBIT"

BYBIT_INTERVALS: dict[str, str] = {
    "1m": "1", "5m": "5", "15m": "15",
    "1h": "60", "4h": "240", "1d": "D", "1w": "W",
}


def to_bybit_pair(symbol: str) -> str:
    return symbol.replace("/", "").upper()


class BybitRestProvider:
    name = "bybit"
    venue_id = "bybit"
    venue_label = "Bybit"

    def __init__(self, timeout: float = 10.0):
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._pairs_cache: list[dict] | None = None
        self._cache_ts: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BYBIT_REST_BASE,
                timeout=self._timeout,
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._client

    def is_symbol_supported(self, symbol: str) -> bool:
        return True

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in BYBIT_INTERVALS

    def supported_symbols(self) -> list[str]:
        return []

    def supported_timeframes(self) -> list[str]:
        return list(BYBIT_INTERVALS.keys())

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        client = await self._get_client()
        pair = to_bybit_pair(symbol)
        interval = BYBIT_INTERVALS.get(timeframe, "60")
        resp = await client.get(
            "/market/kline",
            params={"category": "spot", "symbol": pair, "interval": interval, "limit": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("retCode") != 0:
            raise ValueError(f"Bybit API error: {data}")
        candles: list[Candle] = []
        for raw in data.get("result", {}).get("list", []):
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
        resp = await client.get("/market/tickers", params={"category": "spot"})
        resp.raise_for_status()
        data = resp.json()
        pairs = []
        for t in data.get("result", {}).get("list", []):
            sym = t.get("symbol", "")
            if sym.endswith("USDT"):
                pairs.append({
                    "id": sym,
                    "base": sym.replace("USDT", ""),
                    "quote": "USDT",
                    "venue": "bybit",
                    "display": f"{sym.replace('USDT', '')}/USDT",
                    "volume_24h_quote": float(t.get("turnover24h", 0)),
                    "price": float(t.get("lastPrice", 0)),
                    "change_24h_pct": float(t.get("price24hPcnt", 0)) * 100 if t.get("price24hPcnt") else None,
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


__all__ = ["BybitRestProvider", "BYBIT_REST_BASE", "BYBIT_INTERVALS", "TV_PREFIX", "to_bybit_pair"]

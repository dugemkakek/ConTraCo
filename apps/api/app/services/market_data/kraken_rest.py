"""Kraken REST adapter — OHLCV + full pair listing + TV prefix."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

KRAKEN_REST_BASE = "https://api.kraken.com/0/public"

TV_PREFIX = "KRAKEN"

KRAKEN_INTERVALS: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15,
    "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}

# Kraken uses weird pair names like XBTUSDT, ETHUSDT
# Map common display symbols to Kraken asset pairs
KRAKEN_PAIR_MAP: dict[str, str] = {
    "BTC": "XBT",
    "XBT": "XBT",
    "ETH": "ETH",
    "SOL": "SOL",
    "ADA": "ADA",
    "DOT": "DOT",
    "LINK": "LINK",
    "MATIC": "MATIC",
    "AVAX": "AVAX",
    "XRP": "XRP",
}


def to_kraken_pair(symbol: str) -> str:
    """BTC/USDT -> XBTUSDT, ETH/USDT -> ETHUSDT"""
    base, quote = symbol.split("/")
    base = KRAKEN_PAIR_MAP.get(base, base)
    return f"{base}{quote}"


class KrakenRestProvider:
    name = "kraken"
    venue_id = "kraken"
    venue_label = "Kraken"

    def __init__(self, timeout: float = 10.0):
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._pairs_cache: list[dict] | None = None
        self._cache_ts: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=KRAKEN_REST_BASE,
                timeout=self._timeout,
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._client

    def is_symbol_supported(self, symbol: str) -> bool:
        return True

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in KRAKEN_INTERVALS

    def supported_symbols(self) -> list[str]:
        return []

    def supported_timeframes(self) -> list[str]:
        return list(KRAKEN_INTERVALS.keys())

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        client = await self._get_client()
        pair = to_kraken_pair(symbol)
        interval = KRAKEN_INTERVALS.get(timeframe, 60)
        resp = await client.get(
            "/OHLC",
            params={"pair": pair, "interval": str(interval)},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise ValueError(f"Kraken API error: {data['error']}")
        # Find the correct result key (it's dynamic like XBTUSDT)
        result = data.get("result", {})
        rows = None
        for key, val in result.items():
            if isinstance(val, list):
                rows = val
                break
        if not rows:
            return []
        candles: list[Candle] = []
        for raw in rows[-limit:]:
            try:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(int(raw[0]), tz=timezone.utc),
                    open=float(raw[1]), high=float(raw[2]),
                    low=float(raw[3]), close=float(raw[4]),
                    volume=float(raw[6]),
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
        # Get tickers for all pairs
        resp = await client.get("/Ticker")
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise ValueError(f"Kraken API error: {data['error']}")

        pairs = []
        for raw_pair, t in data.get("result", {}).items():
            if raw_pair.endswith("USDT") or raw_pair.endswith("USD"):
                base = raw_pair.replace("USDT", "").replace("USD", "")
                display_base = next((k for k, v in KRAKEN_PAIR_MAP.items() if v == base), base)
                pairs.append({
                    "id": raw_pair,
                    "base": display_base,
                    "quote": "USDT",
                    "venue": "kraken",
                    "display": f"{display_base}/USDT",
                    "volume_24h_quote": float(t.get("v", [0, 0])[1]) * float(t.get("c", ["0"])[0]),
                    "price": float(t.get("c", ["0"])[0]),
                    "change_24h_pct": ((float(t.get("c", ["0"])[0]) - float(t.get("o", ["0"])[0])) / float(t.get("o", ["0"])[0])) * 100 if float(t.get("o", ["0"])[0]) > 0 else None,
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


__all__ = ["KrakenRestProvider", "KRAKEN_REST_BASE", "KRAKEN_INTERVALS", "TV_PREFIX", "to_kraken_pair"]

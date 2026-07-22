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
BINANCE_REST_FALLBACKS = ("https://data-api.binance.vision/api/v3",)

TV_PREFIX = "BINANCE"

BINANCE_INTERVALS: dict[str, str] = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}


def _ssl_setting() -> bool:
    """Disable SSL verification only when explicitly requested via env.

    Some corporate networks MITM TLS, in which case the system CA bundle
    can't validate Binance's certificate. To keep security defaults safe,
    verification remains on unless the operator explicitly opts out.
    """
    import os
    return os.getenv("BINANCE_VERIFY_SSL", "1") == "1"


def to_binance_pair(symbol: str) -> str:
    return symbol.replace("/", "").upper()


class BinanceRestProvider:
    name = "binance"
    venue_id = "binance"
    venue_label = "Binance"

    BINANCE_FAPI = "https://fapi.binance.com"
    BINANCE_FAPI_FALLBACK = "https://fapi-data-api.binance.vision"

    def __init__(self, timeout: float = 10.0):
        self._client: httpx.AsyncClient | None = None
        self._fapi: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._pairs_cache: list[dict] | None = None
        self._cache_ts: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BINANCE_REST_BASE,
                timeout=self._timeout,
                verify=_ssl_setting(),
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._client

    async def _get_fapi_client(self) -> httpx.AsyncClient:
        if self._fapi is None or self._fapi.is_closed:
            self._fapi = httpx.AsyncClient(
                base_url=self.BINANCE_FAPI,
                timeout=self._timeout,
                verify=_ssl_setting(),
                headers={"User-Agent": "confluence-trading-consultant/1.0"},
            )
        return self._fapi

    async def _get_fapi_with_fallback(self, path: str, *, params: dict) -> httpx.Response:
        client = await self._get_fapi_client()
        for base in (self.BINANCE_FAPI, self.BINANCE_FAPI_FALLBACK):
            try:
                resp = await client.get(f"{base.rstrip('/')}{path}", params=params)
                if resp.status_code == 200 and resp.text.strip().startswith("["):
                    return resp
            except Exception:
                continue
        raise RuntimeError(f"all binance fapi endpoints failed for {path}")

    async def _get_with_fallback(self, path: str, *, params: dict) -> httpx.Response:
        """Try the primary base, then each fallback. Returns the first 2xx."""
        client = await self._get_client()
        for base in (BINANCE_REST_BASE, *BINANCE_REST_FALLBACKS):
            try:
                url = f"{base.rstrip('/')}{path}"
                resp = await client.get(url, params=params)
                if resp.status_code == 200 and resp.text.strip() not in ("", "{}"):
                    return resp
            except Exception:
                continue
        raise RuntimeError(f"all binance endpoints failed for {path}")

    def is_symbol_supported(self, symbol: str) -> bool:
        return True

    def is_timeframe_supported(self, timeframe: str) -> bool:
        return timeframe in BINANCE_INTERVALS

    def supported_symbols(self) -> list[str]:
        return [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
            "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
            "LINK/USDT", "DOT/USDT", "MATIC/USDT", "TRX/USDT",
            "ATOM/USDT", "UNI/USDT", "LTC/USDT", "NEAR/USDT",
            "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
            "PEPE/USDT", "WIF/USDT", "BONK/USDT", "FLOKI/USDT",
        ]

    def supported_timeframes(self) -> list[str]:
        return list(BINANCE_INTERVALS.keys())

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        client = await self._get_client()
        pair = to_binance_pair(symbol)
        interval = BINANCE_INTERVALS.get(timeframe, "1h")
        resp = await self._get_with_fallback(
            "/klines",
            params={"symbol": pair, "interval": interval, "limit": str(limit)},
        )
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
        try:
            resp = await self._get_with_fallback("/ticker/24hr", params={})
        except RuntimeError:
            resp = await client.get("/ticker/24hr")
        data = resp.json() if resp.text.strip() else []  # type: ignore[union-attr]  # noqa: F821
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

    async def get_funding_rate(self, symbol: str) -> dict:
        """Latest USD-M perp funding rate from Binance public futures."""
        pair = to_binance_pair(symbol)
        result = {"symbol": pair, "funding_rate": None, "predicted": None,
                  "next_funding_at": None, "history": []}
        try:
            resp = await self._get_fapi_with_fallback(
                "/fapi/v1/fundingRate", params={"symbol": pair, "limit": 30}
            )
            rows = resp.json() or []
            for r in rows:
                result["history"].append({
                    "funding_time": int(r.get("fundingTime", 0)),
                    "funding_rate": float(r.get("fundingRate", 0) or 0),
                    "mark_price": float(r.get("markPrice", 0) or 0),
                })
            if result["history"]:
                result["funding_rate"] = result["history"][-1]["funding_rate"]
        except Exception:
            pass
        try:
            resp2 = await self._get_fapi_with_fallback(
                "/fapi/v1/premiumIndex", params={"symbol": pair}
            )
            data = resp2.json() or []
            if data:
                result["predicted"] = float(data[0].get("lastFundingRate", 0) or 0)
                result["next_funding_at"] = int(data[0].get("nextFundingTime", 0) or 0)
                result["mark_price"] = float(data[0].get("markPrice", 0) or 0)
        except Exception:
            pass
        return result

    async def get_open_interest(self, symbol: str) -> dict:
        pair = to_binance_pair(symbol)
        try:
            resp = await self._get_fapi_with_fallback(
                "/fapi/v1/openInterest", params={"symbol": pair}
            )
            data = resp.json() or {}
            return {
                "symbol": pair,
                "open_interest": float(data.get("openInterest", 0) or 0),
                "open_interest_value_usd": float(data.get("openInterest", 0) or 0)
                    * float(data.get("markPrice", 0) or 0),
                "source": "binance",
            }
        except Exception as exc:
            return {"symbol": pair, "open_interest": 0.0, "error": str(exc)}

    async def get_long_short_ratio(self, symbol: str) -> dict:
        pair = to_binance_pair(symbol)
        try:
            resp = await self._get_fapi_with_fallback(
                "/futures/data/globalLongShortAccountRatio",
                params={"symbol": pair, "period": "1h", "limit": 30},
            )
            data = resp.json() or []
            return {
                "symbol": pair,
                "long_short_ratio": float(data[-1].get("longShortRatio", 1)) if data else None,
                "history": [
                    {
                        "timestamp": int(d.get("timestamp", 0)),
                        "long_pct": float(d.get("longAccount", 0.5)),
                        "short_pct": float(d.get("shortAccount", 0.5)),
                    }
                    for d in data
                ],
                "source": "binance",
            }
        except Exception as exc:
            return {"symbol": pair, "long_short_ratio": None, "error": str(exc)}

    async def get_orderbook(self, symbol: str, depth: int = 20) -> dict:
        client = await self._get_client()
        resp = await client.get(
            "/depth", params={"symbol": to_binance_pair(symbol), "limit": depth}
        )
        if resp.status_code != 200:
            return {"bids": [], "asks": []}
        data = resp.json()
        return {
            "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
            "lastUpdateId": data.get("lastUpdateId"),
        }


__all__ = ["BinanceRestProvider", "BINANCE_REST_BASE", "BINANCE_INTERVALS", "TV_PREFIX", "to_binance_pair"]  
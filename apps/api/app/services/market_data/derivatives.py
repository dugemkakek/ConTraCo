"""Derivatives data — liquidation heatmap, funding, open interest.

GEO NOTE: Binance fapi.binance.com returns empty 200s in some regions
(Indonesia). Klines + liquidation heatmap use data-api.binance.vision
which works globally. Funding/OI attempt fapi and degrade gracefully
to an honest 'unavailable' flag rather than fabricating data.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BINANCE_VISION = "https://data-api.binance.vision"
BINANCE_FAPI = "https://fapi.binance.com"
TIMEOUT = 15.0


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, verify=False,
                             headers={"User-Agent": "confluence-trading-consultant/1.0"})


async def _get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 240) -> list[dict[str, Any]]:
    """Candles via Binance vision (works globally, no key)."""
    async with _client() as c:
        try:
            r = await c.get(f"{BINANCE_VISION}/api/v3/klines",
                            params={"symbol": symbol.upper(), "interval": interval, "limit": str(limit)})
            if r.status_code != 200 or not r.text.strip().startswith("["):
                return []
            return [{
                "time": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                "low": float(x[3]), "close": float(x[4]), "volume": float(x[5]),
            } for x in r.json()]
        except Exception as exc:
            logger.debug("vision klines %s: %s", symbol, exc)
            return []


def _bucket(price: float, lo: float, hi: float, bins: int) -> int:
    if hi <= lo:
        return 0
    idx = int((price - lo) / (hi - lo) * (bins - 1))
    return max(0, min(bins - 1, idx))


async def get_liquidation_heatmap(
    symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 240, bins: int = 40,
) -> dict[str, Any]:
    """Estimate liquidation clusters from candle structure + leverage tiers.

    Pure candle math — no perp API needed, so it works in geo-blocked regions.
    """
    candles = await _get_klines(symbol=symbol, interval=interval, limit=limit)
    if not candles:
        return {"symbol": symbol.upper(), "bands": [], "current_price": None, "source": "binance-vision"}

    lows = [c["low"] for c in candles]
    highs = [c["high"] for c in candles]
    lo, hi = min(lows), max(highs)

    long_bins = [0.0] * bins
    short_bins = [0.0] * bins
    leverages = [5, 10, 25, 50, 100]

    for c in candles:
        close = c["close"]
        weight = max(c["volume"], 1.0)
        for lev in leverages:
            long_liq = close * (1 - (0.9 / lev))
            short_liq = close * (1 + (0.9 / lev))
            long_bins[_bucket(long_liq, lo, hi, bins)] += weight / lev
            short_bins[_bucket(short_liq, lo, hi, bins)] += weight / lev

    step = (hi - lo) / max(bins, 1)
    bands = []
    for i in range(bins):
        price = lo + step * i
        bands.append({
            "price": round(price, 4),
            "long_score": round(long_bins[i], 4),
            "short_score": round(short_bins[i], 4),
            "total_score": round(long_bins[i] + short_bins[i], 4),
        })

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "current_price": candles[-1]["close"],
        "bands": bands,
        "source": "binance-vision-estimated",
    }


async def get_funding_history(symbol: str = "BTCUSDT", limit: int = 100) -> dict[str, Any]:
    """Funding rate history. Attempts Binance fapi; honest fallback if geo-blocked."""
    async with _client() as c:
        try:
            r = await c.get(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                            params={"symbol": symbol.upper(), "limit": str(limit)})
            if r.status_code == 200 and r.text.strip().startswith("["):
                data = r.json()
                if data:
                    return {
                        "symbol": symbol.upper(),
                        "rows": [{"time": int(x["fundingTime"]), "funding_rate": float(x["fundingRate"])} for x in data],
                        "source": "binance-fapi",
                    }
        except Exception as exc:
            logger.debug("fapi funding %s: %s", symbol, exc)
    return {"symbol": symbol.upper(), "rows": [], "source": "unavailable",
            "note": "fapi.binance.com geo-blocked in this region"}


async def get_open_interest_history(symbol: str = "BTCUSDT", period: str = "5m", limit: int = 100) -> dict[str, Any]:
    """Open interest history. Attempts Binance fapi; honest fallback if geo-blocked."""
    async with _client() as c:
        try:
            r = await c.get(f"{BINANCE_FAPI}/futures/data/openInterestHist",
                            params={"symbol": symbol.upper(), "period": period, "limit": str(limit)})
            if r.status_code == 200 and r.text.strip().startswith("["):
                data = r.json()
                if data:
                    return {
                        "symbol": symbol.upper(), "period": period,
                        "rows": [{"time": int(x["timestamp"]),
                                  "sum_open_interest": float(x["sumOpenInterest"]),
                                  "sum_open_interest_value": float(x["sumOpenInterestValue"])} for x in data],
                        "source": "binance-fapi",
                    }
        except Exception as exc:
            logger.debug("fapi OI %s: %s", symbol, exc)
    return {"symbol": symbol.upper(), "period": period, "rows": [], "source": "unavailable",
            "note": "fapi.binance.com geo-blocked in this region"}

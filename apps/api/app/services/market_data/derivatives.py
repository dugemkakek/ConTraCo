"""Derivatives data — liquidation heatmap, funding, open interest.

GEO NOTE: Binance fapi.binance.com returns empty 200s in some regions
(Indonesia). Klines + liquidation heatmap use data-api.binance.vision
which works globally. Funding/OI use CoinGecko derivatives (free, no
key, no geo-block) as primary, with Binance fapi as fallback.
"""
from __future__ import annotations

import logging
import time as _time
from typing import Any

import httpx

from app.services.market_data.cg_cache import cached_get

logger = logging.getLogger(__name__)

BINANCE_VISION = "https://data-api.binance.vision"
BINANCE_FAPI = "https://fapi.binance.com"
COINGECKO = "https://api.coingecko.com/api/v3"
HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"
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


def _base_coin(symbol: str) -> str:
    return symbol.upper().replace("/USDT", "").replace("-USDT", "").replace("USDT", "")


def _map_hl_funding(data: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Map Hyperliquid fundingHistory payloads to our row shape.

    Skips entries missing a usable time/fundingRate. Keeps the most
    recent `limit` rows.
    """
    rows: list[dict[str, Any]] = []
    for x in data:
        try:
            t = int(x["time"])
            fr = float(x["fundingRate"])
        except (KeyError, TypeError, ValueError):
            continue
        premium = x.get("premium")
        rows.append({
            "time": t,
            "funding_rate": fr,
            "premium": float(premium) if premium is not None else None,
            "exchange": "hyperliquid",
        })
    return rows[-limit:] if limit else rows


async def _fetch_hyperliquid_history(symbol: str, limit: int) -> list[dict[str, Any]] | None:
    """Real hourly funding time series from Hyperliquid's public info API.

    Free, no key, no geo-block (verified reachable from Indonesia where
    Binance fapi is blocked). Only covers coins listed on Hyperliquid;
    returns None for anything else so callers fall through.
    """
    coin = _base_coin(symbol)
    # Funding settles hourly on Hyperliquid; ask for one extra hour so a
    # boundary can't shave the window below `limit` rows.
    start_ms = int(_time.time() * 1000) - (limit + 1) * 3_600_000
    async with _client() as c:
        try:
            r = await c.post(HYPERLIQUID_INFO,
                             json={"type": "fundingHistory", "coin": coin, "startTime": start_ms})
            if r.status_code == 200:
                rows = _map_hl_funding(r.json(), limit)
                if rows:
                    return rows
        except Exception as exc:
            logger.debug("hyperliquid funding %s: %s", symbol, exc)
    return None


async def _fetch_coingecko_funding_snapshot(symbol: str, limit: int) -> list[dict[str, Any]] | None:
    """Current funding across exchanges via CoinGecko derivatives (snapshot, no history)."""
    base = _base_coin(symbol)
    now_ms = int(_time.time() * 1000)
    async with _client() as c:
        try:
            r = await cached_get(c, f"{COINGECKO}/derivatives", params={"include_tickers": "unexpired"})
            if r.status_code == 200:
                rows = []
                for t in r.json():
                    sym = (t.get("symbol") or "").upper().replace("_", "").replace("/", "")
                    if base in sym and "USDT" in sym:
                        fr = t.get("funding_rate")
                        if fr is not None:
                            rows.append({
                                "time": now_ms,
                                "funding_rate": float(fr),
                                "exchange": t.get("market", "unknown"),
                                "basis": t.get("basis"),
                                "index": t.get("index"),
                            })
                if rows:
                    return rows[:limit]
        except Exception as exc:
            logger.debug("coingecko funding %s: %s", symbol, exc)
    return None


async def _fetch_binance_funding(symbol: str, limit: int) -> list[dict[str, Any]] | None:
    """Real funding history from Binance fapi (geo-blocked in some regions)."""
    async with _client() as c:
        try:
            r = await c.get(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                            params={"symbol": symbol.upper(), "limit": str(limit)})
            if r.status_code == 200 and r.text.strip().startswith("["):
                data = r.json()
                if data:
                    return [{"time": int(x["fundingTime"]), "funding_rate": float(x["fundingRate"])} for x in data]
        except Exception as exc:
            logger.debug("fapi funding %s: %s", symbol, exc)
    return None


async def get_funding_history(symbol: str = "BTCUSDT", limit: int = 100) -> dict[str, Any]:
    """Funding rate history — Hyperliquid (primary), CoinGecko, Binance fapi.

    Hyperliquid gives a real hourly time series (free, no key, no
    geo-block) but only for coins it lists. CoinGecko gives a current
    multi-exchange snapshot (no history). Binance fapi gives real history
    but is geo-blocked in some regions (e.g. Indonesia).
    """
    for fetch, source, note in (
        (_fetch_hyperliquid_history, "hyperliquid", "hourly history, single venue"),
        (_fetch_coingecko_funding_snapshot, "coingecko", "current snapshot, multi-exchange"),
        (_fetch_binance_funding, "binance-fapi", None),
    ):
        rows = await fetch(symbol, limit)
        if rows:
            out: dict[str, Any] = {"symbol": symbol.upper(), "rows": rows, "source": source}
            if note:
                out["note"] = note
            return out
    return {"symbol": symbol.upper(), "rows": [], "source": "unavailable",
            "note": "all funding sources unreachable"}


async def get_open_interest_history(symbol: str = "BTCUSDT", period: str = "5m", limit: int = 100) -> dict[str, Any]:
    """Open interest — CoinGecko exchange-level (primary), Binance fapi (fallback).

    CoinGecko gives aggregate OI per exchange in BTC. Binance fapi gives
    per-symbol OI history but is geo-blocked in some regions.
    """
    now_ms = int(_time.time() * 1000)

    # Primary: CoinGecko — exchange-level OI for major perp venues
    async with _client() as c:
        try:
            r = await cached_get(c, f"{COINGECKO}/derivatives/exchanges",
                                 params={"order": "open_interest_btc_desc", "per_page": "20", "page": "1"})
            if r.status_code == 200:
                rows = []
                for ex in r.json():
                    oi_btc = ex.get("open_interest_btc")
                    if oi_btc and float(oi_btc) > 0:
                        rows.append({
                            "time": now_ms,
                            "sum_open_interest": float(oi_btc),
                            "sum_open_interest_value": None,
                            "exchange": ex.get("name", "unknown"),
                        })
                if rows:
                    return {"symbol": symbol.upper(), "period": "snapshot",
                            "rows": rows[:limit], "source": "coingecko",
                            "note": "exchange-level OI in BTC, current snapshot"}
        except Exception as exc:
            logger.debug("coingecko OI %s: %s", symbol, exc)

    # Fallback: Binance fapi
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
            "note": "all OI sources unreachable"}

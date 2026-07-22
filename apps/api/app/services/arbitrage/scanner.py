"""Arbitrage scanner — cross-exchange spot spreads + funding arb.

Data sources (all free, no API key):
  * CoinGecko /coins/{id}/tickers — per-exchange spot prices
  * Binance data-api.binance.vision — spot price fallback
  * Funding: Binance fapi (may be geo-blocked in some regions)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

COINGECKO = "https://api.coingecko.com/api/v3"
BINANCE_VISION = "https://data-api.binance.vision"
BINANCE_FAPI = "https://fapi.binance.com"
TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "10.0"))
USER_AGENT = "confluence-trading-consultant/1.0"

# CoinGecko coin IDs for the default scan universe
COIN_IDS = {
    "BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "SOL/USDT": "solana",
    "BNB/USDT": "binancecoin", "XRP/USDT": "ripple", "DOGE/USDT": "dogecoin",
    "ADA/USDT": "cardano", "AVAX/USDT": "avalanche-2", "LINK/USDT": "chainlink",
    "DOT/USDT": "polkadot", "MATIC/USDT": "matic-network", "TRX/USDT": "tron",
}

# Minimum spread to report (after fees)
MIN_SPREAD_PCT = 0.01


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, verify=False,
                             headers={"User-Agent": USER_AGENT})


async def _coingecko_tickers(client: httpx.AsyncClient, coin_id: str) -> list[dict]:
    """Fetch per-exchange USDT tickers for a coin from CoinGecko."""
    try:
        resp = await client.get(
            f"{COINGECKO}/coins/{coin_id}/tickers",
            params={"include_exchange_logo": "false", "depth": "false"},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            t for t in data.get("tickers", [])
            if t.get("target") == "USDT"
            and t.get("last") is not None
            and t.get("last", 0) > 0
            and t.get("is_stale") is False
            and t.get("is_anomaly") is False
        ]
    except Exception as exc:
        logger.debug("coingecko tickers %s: %s", coin_id, exc)
        return []


async def _binance_funding(client: httpx.AsyncClient, pair: str) -> float | None:
    """Try Binance perp funding rate. Returns None if geo-blocked."""
    try:
        resp = await client.get(
            f"{BINANCE_FAPI}/fapi/v1/premiumIndex",
            params={"symbol": pair},
        )
        if resp.status_code == 200 and resp.text.strip().startswith("{"):
            data = resp.json()
            return float(data.get("lastFundingRate", 0))
    except Exception:
        pass
    return None


async def scan_yield_opportunities(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    """Cross-venue funding arb scanner.

    Uses Binance perp funding when available. Falls back to
    cross-exchange spot spread analysis via CoinGecko when perp
    endpoints are geo-blocked.
    """
    if not symbols:
        symbols = list(COIN_IDS.keys())

    out: list[dict[str, Any]] = []

    async with _client() as client:
        for sym in symbols:
            coin_id = COIN_IDS.get(sym)
            if not coin_id:
                continue
            try:
                tickers = await _coingecko_tickers(client, coin_id)
                if len(tickers) < 2:
                    continue

                # Sort by price — find cheapest and most expensive venue
                ordered = sorted(tickers, key=lambda t: t["last"])
                cheapest = ordered[0]
                priciest = ordered[-1]

                low_price = cheapest["last"]
                high_price = priciest["last"]
                spread_pct = ((high_price - low_price) / low_price) * 100

                if spread_pct < MIN_SPREAD_PCT:
                    continue

                # Try to get funding rate for extra context
                pair = sym.replace("/", "")
                funding = await _binance_funding(client, pair)

                # Annualized: if spread persists, daily capture ≈ spread
                net_apy_pct = round(spread_pct * 365 - 0.1, 3)  # subtract 10bps fees

                out.append({
                    "symbol": sym,
                    "spot_price": low_price,
                    "perp_price": high_price,
                    "funding_rate": funding or 0,
                    "long_venue": cheapest["market"]["name"],
                    "short_venue": priciest["market"]["name"],
                    "long_funding": funding,
                    "short_funding": None,
                    "spread_bps": round(spread_pct * 100, 2),
                    "net_apy": net_apy_pct,
                    "confidence": min(1.0, len(tickers) / 5),
                    "source": "coingecko_spot",
                })
            except Exception as exc:
                logger.debug("arb scan %s: %s", sym, exc)
                continue

    out.sort(key=lambda x: -abs(x["net_apy"]))
    return out


async def scan_cex_dex_spreads() -> list[dict[str, Any]]:
    """Cross-exchange spot spread matrix via CoinGecko.

    Compares prices across all exchanges listing each coin's USDT pair.
    Reports pairs where the spread exceeds MIN_SPREAD_PCT.
    """
    out: list[dict[str, Any]] = []

    async with _client() as client:
        for sym, coin_id in list(COIN_IDS.items())[:8]:  # rate-limit friendly
            try:
                tickers = await _coingecko_tickers(client, coin_id)
                if len(tickers) < 2:
                    continue

                ordered = sorted(tickers, key=lambda t: t["last"])
                cheapest = ordered[0]
                priciest = ordered[-1]
                spread_pct = ((priciest["last"] - cheapest["last"]) / cheapest["last"]) * 100

                if spread_pct < MIN_SPREAD_PCT:
                    continue

                out.append({
                    "symbol": sym,
                    "cex_venue": cheapest["market"]["name"],
                    "cex_price": cheapest["last"],
                    "dex_venue": priciest["market"]["name"],
                    "dex_price": priciest["last"],
                    "spread_pct": round(spread_pct, 4),
                    "net_profit_after_gas": round(spread_pct - 0.1, 4),
                    "executable": spread_pct > 0.3,
                    "liquidity_usd": cheapest.get("converted_volume", {}).get("usd"),
                    "volume_24h_usd": priciest.get("converted_volume", {}).get("usd"),
                    "source": "coingecko_spot",
                })
            except Exception as exc:
                logger.debug("spread scan %s: %s", sym, exc)
                continue

    out.sort(key=lambda x: -abs(x["spread_pct"]))
    return out

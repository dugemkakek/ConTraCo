"""Arbitrage scanner — live cross-venue spreads, funding-rate opportunities, DEX/CEX disparity.

Data sources:
  * Binance spot + perp funding (free public REST)
  * Bybit public perp funding
  * OKX public perp funding
  * CoinGecko for global prices
  * Uniswap v3 (The Graph) on Ethereum + Base for CEX-vs-DEX disparity
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_FAPI_FALLBACK = "https://fapi-data-api.binance.vision"
BINANCE_REST = "https://api.binance.com"
BINANCE_VISION = "https://data-api.binance.vision"
BYBIT_REST = "https://api.bybit.com"
OKX_REST = "https://www.okx.com"

VERIFY_SSL = os.getenv("FREE_PROVIDER_VERIFY_SSL", "1") == "1"
TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "8.0"))
USER_AGENT = "confluence-trading-consultant/1.0"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, verify=VERIFY_SSL,
                             headers={"User-Agent": USER_AGENT})


async def _get(client: httpx.AsyncClient, url: str, params: dict, bases: tuple = ()) -> dict | None:
    """GET, trying the primary URL first then any ``bases``-suffixed fallbacks."""
    urls = [url]
    for b in bases:
        urls.append(url.replace(BINANCE_FAPI, b))
    for u in urls:
        try:
            resp = await client.get(u, params=params)
            if resp.status_code == 200 and resp.text.strip().startswith(("{")):
                return resp.json()
        except Exception:
            continue
    return None


def _normalize_pair(symbol: str) -> str:
    """Convert 'BTC/USDT' to 'BTCUSDT' for venue-specific endpoints."""
    return symbol.replace("/", "").upper()


async def _spot_price(client: httpx.AsyncClient, symbol: str) -> float | None:
    """Live spot price via Binance with the data-api vision fallback."""
    pair = _normalize_pair(symbol)
    for base in (BINANCE_VISION, BINANCE_REST):
        try:
            resp = await client.get(f"{base}/api/v3/ticker/price", params={"symbol": pair})
            if resp.status_code == 200 and resp.text.strip().startswith("{"):
                data = resp.json()
                return float(data.get("price", 0) or 0)
        except Exception:
            continue
    return None


async def _binance_perp(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """Bin Perp mark + funding. Returns dict with spot-like fields."""
    pair = _normalize_pair(symbol)
    funding = await _get(
        client,
        f"{BINANCE_FAPI}/fapi/v1/fundingRate",
        {"symbol": pair, "limit": 5},
        bases=(BINANCE_FAPI_FALLBACK,),
    )
    premium = await _get(
        client,
        f"{BINANCE_FAPI}/fapi/v1/premiumIndex",
        {"symbol": pair},
        bases=(BINANCE_FAPI_FALLBACK,),
    )
    oi = await _get(
        client,
        f"{BINANCE_FAPI}/fapi/v1/openInterest",
        {"symbol": pair},
        bases=(BINANCE_FAPI_FALLBACK,),
    )
    if not funding or not premium:
        return None
    funding_rate = float(premium.get("lastFundingRate", 0)) if premium else 0
    mark_price = float(premium.get("markPrice", 0)) if premium else 0
    last_funding = float(funding[0]["fundingRate"]) if funding else 0
    return {
        "funding_rate": last_funding,
        "predicted_funding": funding_rate,
        "mark_price": mark_price,
        "open_interest": float(oi.get("openInterest", 0)) if oi else 0,
        "venue": "binance",
    }


async def _bybit_perp(client: httpx.AsyncClient, symbol: str) -> dict | None:
    try:
        resp = await client.get(
            f"{BYBIT_REST}/v5/markets/tickers",
            params={"category": "linear", "symbol": _normalize_pair(symbol)},
        )
        if resp.status_code != 200:
            return None
        rows = ((resp.json() or {}).get("result") or {}).get("list") or []
        if not rows:
            return None
        row = rows[0]
        return {
            "funding_rate": float(row.get("fundingRate", 0) or 0),
            "predicted_funding": float(row.get("nextFundingRate", 0) or 0),
            "mark_price": float(row.get("markPrice", 0) or 0),
            "open_interest": float(row.get("openInterest", 0) or 0),
            "venue": "bybit",
        }
    except Exception:
        return None


async def _okx_perp(client: httpx.AsyncClient, symbol: str) -> dict | None:
    pair = _normalize_pair(symbol)
    okx_pair = f"{pair[:-4]}-USDT-SWAP" if pair.endswith("USDT") else pair
    try:
        resp = await client.get(f"{OKX_REST}/api/v5/market/ticker",
                                params={"instId": okx_pair})
        if resp.status_code != 200:
            return None
        rows = (resp.json() or {}).get("data") or []
        if not rows:
            return None
        row = rows[0]
        return {
            "funding_rate": float(row.get("fundingRate", 0) or 0),
            "predicted_funding": None,
            "mark_price": float(row.get("markPx", 0) or 0),
            "open_interest": 0,
            "venue": "okx",
        }
    except Exception:
        return None


async def scan_yield_opportunities(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    """Cross-venue funding arb scanner.

    For each symbol, fetch spot from Binance + perp funding from
    Binance/Bybit/OKX. Compute net APY as
    ``funding * 8h/day * 365d - fees_basis_points``.

    Returns only opportunities where any two venues disagree on
    funding sign or absolute level — i.e. real, actionable.
    """
    if not symbols:
        symbols = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
            "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
            "LINK/USDT", "MATIC/USDT", "DOT/USDT", "TRX/USDT",
        ]

    out: list[dict[str, Any]] = []

    async with _client() as client:
        for sym in symbols:
            try:
                spot = await _spot_price(client, sym)
                bnb_perp, bybit_perp, okx_perp = await asyncio.gather(
                    _binance_perp(client, sym),
                    _bybit_perp(client, sym),
                    _okx_perp(client, sym),
                    return_exceptions=True,
                )

                venues: dict[str, dict[str, Any]] = {}
                for v, payload in (("binance", bnb_perp), ("bybit", bybit_perp),
                                    ("okx", okx_perp)):
                    if isinstance(payload, dict) and payload:
                        venues[v] = payload  # type: ignore[assignment]

                if not venues or not spot:
                    continue

                # Find lowest and highest funding venue
                ordered = sorted(
                    venues.items(),
                    key=lambda kv: kv[1].get("funding_rate", 0) or 0,
                )
                short_venue, short_payload = ordered[0]
                long_venue, long_payload = ordered[-1]

                basis = (long_payload["funding_rate"] - short_payload["funding_rate"])
                # Annualised: 3 funding events/day (8h) * 365 = 1095 events/yr
                net_apy_pct = basis * 3 * 365 * 100 - 0.05  # subtract 5bps round-trip fee budget
                net_apy_pct = round(net_apy_pct, 3)
                if abs(net_apy_pct) < 1.0 or len(ordered) < 1:
                    continue

                out.append({
                    "symbol": sym,
                    "spot_price": spot,
                    "long_venue": long_venue,
                    "short_venue": short_venue,
                    "long_funding": long_payload.get("funding_rate"),
                    "short_funding": short_payload.get("funding_rate"),
                    "spread_bps": round(basis * 10000, 2),
                    "net_apy": net_apy_pct,
                    "confidence": 1.0 if len(venues) >= 2 else 0.6,
                    "venue_snapshot": venues,
                    "source": "live",
                })
            except Exception as exc:  # noqa: BLE001
                logger.debug("arb scan %s failed: %s", sym, exc)
                continue

    out.sort(key=lambda x: -(abs(x["net_apy"])))
    return out


async def scan_cex_dex_spreads() -> list[dict[str, Any]]:
    """Cross-reference Binance spot vs Uniswap v3 pools on Ethereum.

    Returns spread opportunities when DEX price differs from Binance
    by more than 0.5%. Reads the top Uniswap pools via the public
    free-tier subgraph; if unavailable, returns empty (no fabrication).
    """
    from app.services.market_data.dex import list_top_pools

    pairs = await list_top_pools(network="ethereum", limit=20)
    if "pools" not in pairs or not pairs["pools"]:
        return []

    out: list[dict[str, Any]] = []
    async with _client() as client:
        for p in pairs["pools"]:
            base = (p.get("base") or "").upper()
            quote = (p.get("quote") or "").upper()
            if quote != "USDT" and quote != "USDC" and quote != "WETH":
                continue
            cex_symbol = f"{base}/USDT" if quote in ("USDT", "USDC") else f"{base}/ETH"
            cex_price = await _spot_price(client, cex_symbol) if base != "WETH" else None
            if not cex_price:
                continue
            dex_price_usd = float(p.get("price", 0) or 0) * (
                await _spot_price(client, "ETH/USDT") if quote == "WETH" else 1.0
            )
            spread_pct = ((dex_price_usd - cex_price) / cex_price) * 100 if cex_price else 0
            if abs(spread_pct) < 0.5:
                continue
            out.append({
                "symbol": cex_symbol,
                "cex_venue": "binance",
                "dex_venue": "uniswap_v3",
                "cex_price": cex_price,
                "dex_price": round(dex_price_usd, 6),
                "spread_pct": round(spread_pct, 2),
                "liquidity_usd": p.get("liquidity_usd"),
                "volume_24h_usd": p.get("volume_24h_usd"),
                "pool_address": p.get("address"),
                "source": "live",
            })
    out.sort(key=lambda x: -abs(x["spread_pct"]))
    return out

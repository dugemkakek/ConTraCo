"""DEX Sniping — detect new token launches and pools in real-time.

Uses GeckoTerminal public REST API (no key required) to surface:
  * Newly created pools on any supported network in the last N minutes
  * Token launch metadata (initial liquidity, creator address, pair)
  * Simple rug-risk scoring based on liquidity concentration

This is a READ-ONLY intelligence layer — it detects opportunities but
does NOT build, sign, or submit transactions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GECKO_BASE = "https://api.geckoterminal.com/api/v2"
_HTTP_TIMEOUT = 12.0

NETWORK_SLUGS: dict[str, str] = {
    "ethereum": "eth",
    "base": "base",
    "polygon": "polygon_pos",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "bsc": "bsc",
    "solana": "solana",
    "avalanche": "avax",
}


def _slug(network: str) -> str:
    return NETWORK_SLUGS.get(network.lower(), network.lower())


async def get_new_pools(
    network: str = "ethereum",
    minutes_back: int = 60,
    limit: int = 20,
) -> dict[str, Any]:
    """Fetch pools created in the last ``minutes_back`` minutes.

    Returns a dict with ``pools`` list, each item containing:
      address, name, base_token, quote_token, created_at,
      initial_liquidity_usd, volume_1h_usd, rug_risk_score (0-1)
    """
    slug = _slug(network)
    url = f"{GECKO_BASE}/networks/{slug}/new_pools"
    params = {"page": 1, "per_page": min(limit, 100)}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            raw = resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"GeckoTerminal HTTP {e.response.status_code}", "pools": []}
        except Exception as e:
            return {"error": str(e), "pools": []}

    now_ts = time.time()
    cutoff_ts = now_ts - minutes_back * 60
    pools = []
    for item in raw.get("data", []):
        attrs = item.get("attributes", {})
        created_str = attrs.get("pool_created_at") or ""
        # Parse ISO8601 timestamp
        try:
            from datetime import datetime, timezone
            if created_str:
                dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                created_ts = dt.timestamp()
            else:
                created_ts = 0
        except Exception:
            created_ts = 0

        if created_ts and created_ts < cutoff_ts:
            continue

        liq = float(attrs.get("reserve_in_usd") or 0)
        vol_1h = float(attrs.get("volume_usd", {}).get("h1") or 0)

        # Simple rug-risk heuristic: low liquidity + high early volume = suspicious
        rug_score = 0.0
        if liq < 5_000:
            rug_score += 0.5
        if liq > 0 and vol_1h / liq > 5:
            rug_score += 0.3
        if liq < 1_000:
            rug_score += 0.2
        rug_score = min(rug_score, 1.0)

        relationships = item.get("relationships", {})
        base_token = relationships.get("base_token", {}).get("data", {}).get("id", "")
        quote_token = relationships.get("quote_token", {}).get("data", {}).get("id", "")

        pools.append({
            "address": attrs.get("address", ""),
            "name": attrs.get("name", ""),
            "network": network,
            "dex": attrs.get("dex_id", ""),
            "base_token": base_token.split("_")[-1] if "_" in base_token else base_token,
            "quote_token": quote_token.split("_")[-1] if "_" in quote_token else quote_token,
            "created_at": created_str,
            "initial_liquidity_usd": liq,
            "volume_1h_usd": vol_1h,
            "price_usd": float(attrs.get("base_token_price_usd") or 0),
            "transactions_1h": attrs.get("transactions", {}).get("h1", {}).get("buys", 0),
            "rug_risk_score": round(rug_score, 2),
        })

    pools.sort(key=lambda p: p["initial_liquidity_usd"], reverse=True)
    return {
        "network": network,
        "minutes_back": minutes_back,
        "total_found": len(pools),
        "pools": pools[:limit],
    }


async def get_trending_pools(
    network: str = "ethereum",
    limit: int = 10,
) -> dict[str, Any]:
    """Trending pools by 5-min volume on the given network."""
    slug = _slug(network)
    url = f"{GECKO_BASE}/networks/{slug}/trending_pools"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            return {"error": str(e), "pools": []}

    pools = []
    for item in raw.get("data", [])[:limit]:
        attrs = item.get("attributes", {})
        pools.append({
            "address": attrs.get("address", ""),
            "name": attrs.get("name", ""),
            "price_usd": float(attrs.get("base_token_price_usd") or 0),
            "price_change_5m": float(attrs.get("price_change_percentage", {}).get("m5") or 0),
            "volume_5m_usd": float(attrs.get("volume_usd", {}).get("m5") or 0),
            "liquidity_usd": float(attrs.get("reserve_in_usd") or 0),
            "transactions_5m_buys": attrs.get("transactions", {}).get("m5", {}).get("buys", 0),
        })
    return {"network": network, "pools": pools}


async def multi_network_snipe_scan(
    networks: list[str] | None = None,
    minutes_back: int = 30,
    min_liquidity_usd: float = 10_000,
    max_rug_risk: float = 0.5,
) -> dict[str, Any]:
    """Parallel snipe scan across multiple networks.

    Filters results by minimum liquidity and maximum rug risk threshold.
    """
    target_networks = networks or ["ethereum", "base", "arbitrum", "polygon"]
    tasks = [get_new_pools(net, minutes_back=minutes_back, limit=50) for net in target_networks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_pools: list[dict] = []
    errors: list[str] = []
    for net, result in zip(target_networks, results):
        if isinstance(result, Exception):
            errors.append(f"{net}: {result}")
            continue
        if "error" in result:
            errors.append(f"{net}: {result['error']}")
            continue
        for pool in result.get("pools", []):
            if (
                pool.get("initial_liquidity_usd", 0) >= min_liquidity_usd
                and pool.get("rug_risk_score", 1.0) <= max_rug_risk
            ):
                all_pools.append(pool)

    all_pools.sort(key=lambda p: p["initial_liquidity_usd"], reverse=True)
    return {
        "networks_scanned": target_networks,
        "minutes_back": minutes_back,
        "filters": {"min_liquidity_usd": min_liquidity_usd, "max_rug_risk": max_rug_risk},
        "total_opportunities": len(all_pools),
        "pools": all_pools[:40],
        "errors": errors,
    }


__all__ = [
    "NETWORK_SLUGS",
    "get_new_pools",
    "get_trending_pools",
    "multi_network_snipe_scan",
]

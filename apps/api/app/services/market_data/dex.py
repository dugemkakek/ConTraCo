"""DEX integration — Uniswap v3 reads + Robinhood/base tranche discovery.

Provides read-only DEX data. **No execution, no signing, no wallet
interaction.** This satisfies the project's recommend-only boundary.

Covered surfaces:
  * Uniswap v3 pool pricing + 24h volume + TVL (Ethereum, Polygon,
    Arbitrum, Optimism, Base)
  * Robinhood on-chain tokenized product discovery on Base (via The Graph)
  * Top pools by TVL per network
  * Best-route estimator for quotes (read-only: returns pool hop
    candidates without constructing a transaction)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from app.services.market_data.free_sources import (
    ProviderResult,
    fetch_top_uniswap_pools,
    fetch_uniswap_v3_pool,
)

logger = logging.getLogger(__name__)

SUPPORTED_NETWORKS = ("ethereum", "polygon", "arbitrum", "optimism", "base")


def _validate_network(network: str) -> str:
    network = (network or "ethereum").lower()
    if network not in SUPPORTED_NETWORKS:
        raise ValueError(
            f"Unsupported network {network!r}. Supported: {SUPPORTED_NETWORKS}"
        )
    return network


async def get_pool(pool_address: str, network: str = "ethereum") -> dict[str, Any]:
    """Single pool read. Returns the snapshot or ``error`` key on failure."""
    network = _validate_network(network)
    res: ProviderResult = await fetch_uniswap_v3_pool(pool_address, network=network)
    if res.error or res.value is None:
        return {"error": res.error or "no data"}
    return res.value


async def list_top_pools(network: str = "ethereum", limit: int = 20) -> dict[str, Any]:
    """Top pools by TVL on the given network."""
    network = _validate_network(network)
    res: ProviderResult = await fetch_top_uniswap_pools(network=network, limit=limit)
    if res.error or res.value is None:
        return {"error": res.error or "no data", "network": network, "pools": []}
    return res.value


async def discover_robinhood_tranches_on_base(limit: int = 25) -> dict[str, Any]:
    """Find the most-liquid tokenized-product pools on Base.

    Robinhood tokenized-equity product (HOOD) and similar assets issue
    ERC-20s on Base that trade in Uniswap v3 pools there. Returns the
    top pools whose token contains a ticker hint, ordered by TVL.
    """
    res: ProviderResult = await fetch_top_uniswap_pools(network="base", limit=limit)
    if res.error or not isinstance(res.value, dict):
        return {"error": res.error or "no data", "network": "base", "tranches": []}
    candidates = []
    hints = ("RH", "HOOD", "ROBIN", "TRCH", "XTR", "TBILL", "RWA")
    for pool in res.value.get("pools", []):
        syms = (pool.get("base", ""), pool.get("quote", ""))
        if any(h in (s or "").upper() for s in syms for h in hints):
            candidates.append(pool)
    return {"network": "base", "tranches": candidates}


async def best_route_quote(
    token_in: str,
    token_out: str,
    amount_in: float,
    network: str = "ethereum",
) -> dict[str, Any]:
    """Indicative route calculation (no transaction built).

    Returns the top pool whose pair matches the requested tokens,
    the implied output given amount_in and token decimals.
    """
    network = _validate_network(network)
    res: ProviderResult = await fetch_top_uniswap_pools(network=network, limit=50)
    if res.error or not isinstance(res.value, dict):
        return {"error": res.error or "no data"}
    syms_in = {token_in.upper(), token_out.upper()}
    matches = [
        p for p in res.value.get("pools", [])
        if {p.get("base", "").upper(), p.get("quote", "").upper()} == syms_in
    ]
    if not matches:
        return {"error": "no matching pool", "tried": syms_in}
    best = matches[0]
    price = best.get("price", 0.0)
    if token_in.upper() == best.get("base", "").upper():
        implied_out = amount_in * float(price)
    else:
        implied_out = amount_in / float(price) if price else 0.0
    return {
        "network": network,
        "pool": best.get("address"),
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": amount_in,
        "amount_out_estimate": implied_out,
        "price": price,
        "liquidity_usd": best.get("liquidity_usd"),
        "fee_tier": best.get("fee_tier"),
    }


async def aggregate_network_state(network: str = "ethereum") -> dict[str, Any]:
    """Aggregate top-25 DEX pool + TVL for a network.

    Convenient one-shot for the dashboard's "DEX activity" panel.
    """
    pools = await list_top_pools(network=network, limit=25)
    if "error" in pools:
        return pools
    total_liquidity = sum(p.get("liquidity_usd", 0) for p in pools.get("pools", []))
    total_volume_24h = sum(p.get("volume_24h_usd", 0) for p in pools.get("pools", []))
    return {
        "network": network,
        "pool_count": len(pools.get("pools", [])),
        "total_liquidity_usd": total_liquidity,
        "total_volume_24h_usd": total_volume_24h,
        "top_pools": pools.get("pools", [])[:10],
    }


__all__ = [
    "SUPPORTED_NETWORKS",
    "get_pool",
    "list_top_pools",
    "discover_robinhood_tranches_on_base",
    "best_route_quote",
    "aggregate_network_state",
]

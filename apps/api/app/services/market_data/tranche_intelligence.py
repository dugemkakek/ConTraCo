"""DEX Tranche Intelligence — advanced pool analysis for Uniswap v3 positions.

Provides:
  * Fee tier scoring across pool candidates
  * Concentrated liquidity range profitability estimation
  * Cross-pool TVL ranking and volume efficiency
  * Tranche grouping: cluster pools by token pair + fee tier

All reads via The Graph / GeckoTerminal public APIs.
No execution, no signing.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.services.market_data.dex import list_top_pools, aggregate_network_state

logger = logging.getLogger(__name__)

GECKO_BASE = "https://api.geckoterminal.com/api/v2"
_HTTP_TIMEOUT = 15.0

# Uniswap v3 fee tiers (bps → label)
FEE_TIER_LABELS: dict[int, str] = {
    100: "Stable (0.01%)",
    500: "Low (0.05%)",
    3000: "Standard (0.30%)",
    10000: "Exotic (1.00%)",
}


def _score_fee_tier(fee_bps: int, volatility_hint: str = "medium") -> float:
    """Score a fee tier 0-1 given asset volatility context."""
    scores = {
        "stable": {100: 1.0, 500: 0.8, 3000: 0.3, 10000: 0.1},
        "low": {100: 0.5, 500: 1.0, 3000: 0.6, 10000: 0.2},
        "medium": {100: 0.2, 500: 0.7, 3000: 1.0, 10000: 0.5},
        "high": {100: 0.1, 500: 0.3, 3000: 0.8, 10000: 1.0},
    }
    tier_map = scores.get(volatility_hint.lower(), scores["medium"])
    # Normalize fee_bps to nearest standard tier
    candidates = sorted(FEE_TIER_LABELS.keys(), key=lambda f: abs(f - fee_bps))
    return tier_map.get(candidates[0], 0.5)


def _volume_efficiency(volume_24h: float, liquidity: float) -> float:
    """Capital efficiency = volume_24h / liquidity. Higher = better LP yield."""
    if liquidity <= 0:
        return 0.0
    return round(volume_24h / liquidity, 4)


async def analyze_pool_tranches(
    network: str = "ethereum",
    token_pair: str | None = None,
    volatility: str = "medium",
    limit: int = 30,
) -> dict[str, Any]:
    """Analyze and rank pool tranches for LP opportunity.

    For each pool found on the network:
      * Calculates fee tier score given volatility context
      * Calculates volume efficiency (volume/TVL ratio)
      * Groups by token pair
      * Returns ranked tranches with recommended fee tier

    Args:
        network: one of ethereum, base, polygon, arbitrum, optimism
        token_pair: optional filter e.g. "ETH/USDC" (loose match on symbols)
        volatility: stable | low | medium | high — drives fee tier scoring
        limit: max pools to analyze
    """
    pools_data = await list_top_pools(network=network, limit=limit)
    if "error" in pools_data:
        return {"error": pools_data["error"]}

    pools = pools_data.get("pools", [])
    if token_pair:
        tokens = [t.strip().upper() for t in token_pair.replace("/", " ").split()]
        pools = [
            p for p in pools
            if any(tok in (p.get("base", "") or "").upper() for tok in tokens)
            or any(tok in (p.get("quote", "") or "").upper() for tok in tokens)
        ]

    tranches: list[dict] = []
    pair_groups: dict[str, list] = {}

    for pool in pools:
        base = pool.get("base", "").upper()
        quote = pool.get("quote", "").upper()
        fee_bps = int(pool.get("fee_tier") or 3000)
        liq = float(pool.get("liquidity_usd") or 0)
        vol = float(pool.get("volume_24h_usd") or 0)

        fee_score = _score_fee_tier(fee_bps, volatility)
        vol_eff = _volume_efficiency(vol, liq)
        # Composite score: fee suitability × sqrt(volume_efficiency)
        composite = round(fee_score * (vol_eff ** 0.5 + 0.1), 4)

        entry = {
            "address": pool.get("address", ""),
            "pair": f"{base}/{quote}",
            "fee_tier_bps": fee_bps,
            "fee_tier_label": FEE_TIER_LABELS.get(fee_bps, f"{fee_bps/100:.2f}%"),
            "fee_tier_score": round(fee_score, 3),
            "liquidity_usd": liq,
            "volume_24h_usd": vol,
            "volume_efficiency": vol_eff,
            "composite_score": composite,
        }
        tranches.append(entry)
        pair_key = f"{base}/{quote}"
        pair_groups.setdefault(pair_key, []).append(entry)

    tranches.sort(key=lambda t: t["composite_score"], reverse=True)

    # Best tranche per pair
    best_per_pair = {}
    for pair, group in pair_groups.items():
        best = max(group, key=lambda t: t["composite_score"])
        best_per_pair[pair] = {
            "recommended_fee_tier": best["fee_tier_label"],
            "composite_score": best["composite_score"],
            "pool_address": best["address"],
            "alternatives": len(group) - 1,
        }

    return {
        "network": network,
        "volatility_context": volatility,
        "token_pair_filter": token_pair,
        "pools_analyzed": len(tranches),
        "top_tranches": tranches[:10],
        "best_per_pair": best_per_pair,
    }


async def get_pool_position_profitability(
    pool_address: str,
    network: str = "ethereum",
    investment_usd: float = 10_000,
    price_range_pct: float = 20.0,
) -> dict[str, Any]:
    """Estimate LP position profitability for a concentrated liquidity range.

    Given an investment amount and ±price_range_pct around the current price,
    estimates:
      * Daily fee earnings based on current pool volume share
      * Impermanent loss at range boundaries
      * Break-even days

    DISCLAIMER: This is an educational estimate only, not financial advice.
    """
    from app.services.market_data.dex import get_pool
    pool = await get_pool(pool_address, network=network)
    if "error" in pool:
        return {"error": pool["error"]}

    liq = float(pool.get("liquidity_usd") or 0)
    vol_24h = float(pool.get("volume_24h_usd") or 0)
    fee_bps = int(pool.get("fee_tier") or 3000)
    price = float(pool.get("price") or 0)

    if liq <= 0 or vol_24h <= 0:
        return {"error": "Insufficient pool data for analysis", "pool": pool_address}

    fee_pct = fee_bps / 1_000_000  # bps to decimal
    # Estimate your share of pool liquidity in range
    price_range_fraction = price_range_pct / 100
    # Concentrated liquidity amplifies position ~(1/range_fraction) vs full range
    concentration_multiplier = min(1 / (2 * price_range_fraction), 20.0)
    effective_share = (investment_usd / liq) * concentration_multiplier
    daily_fees = vol_24h * fee_pct * effective_share

    # Impermanent loss at boundary (full price_range_pct move)
    # IL approximation for concentrated range: 2*sqrt(r)-1-r where r = price_ratio
    import math
    r = 1 + price_range_fraction
    il_at_boundary_pct = round((2 * math.sqrt(r) - 1 - r) * 100, 2)

    break_even_days = investment_usd / daily_fees if daily_fees > 0 else None

    return {
        "pool": pool_address,
        "network": network,
        "investment_usd": investment_usd,
        "price_range_pct": price_range_pct,
        "current_price": price,
        "fee_tier_label": FEE_TIER_LABELS.get(fee_bps, f"{fee_bps/100:.2f}%"),
        "estimated_daily_fee_usd": round(daily_fees, 4),
        "estimated_apy_pct": round(daily_fees * 365 / investment_usd * 100, 2),
        "il_at_range_boundary_pct": il_at_boundary_pct,
        "break_even_days": round(break_even_days, 1) if break_even_days else None,
        "disclaimer": "Estimate only. IL and fees depend on actual price movements and volume.",
    }


async def tranche_leaderboard(
    networks: list[str] | None = None,
    volatility: str = "medium",
) -> dict[str, Any]:
    """Cross-network tranche leaderboard — top composite scoring pools."""
    import asyncio
    target = networks or ["ethereum", "base", "arbitrum"]
    tasks = [analyze_pool_tranches(net, volatility=volatility, limit=20) for net in target]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tranches: list[dict] = []
    for net, res in zip(target, results):
        if isinstance(res, Exception) or "error" in (res or {}):
            continue
        for t in (res or {}).get("top_tranches", []):
            all_tranches.append({**t, "network": net})

    all_tranches.sort(key=lambda t: t["composite_score"], reverse=True)
    return {
        "networks": target,
        "volatility_context": volatility,
        "total_tranches": len(all_tranches),
        "leaderboard": all_tranches[:20],
    }


__all__ = [
    "FEE_TIER_LABELS",
    "analyze_pool_tranches",
    "get_pool_position_profitability",
    "tranche_leaderboard",
]

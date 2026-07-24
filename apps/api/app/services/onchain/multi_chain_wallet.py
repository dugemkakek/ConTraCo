"""Multi-chain wallet analyzer — normalized portfolio + council scoring.

Wraps the existing single-chain wallet_tracker primitives into a
cross-chain view the AI council can consume.
"""
from __future__ import annotations

from typing import Any

from app.services.onchain.wallet_tracker import get_wallet_token_balances, score_wallet

DEFAULT_CHAINS = ["eth", "base", "arbitrum", "optimism", "polygon"]


async def analyze_wallet_multi_chain(address: str, chains: list[str] | None = None) -> dict[str, Any]:
    targets = chains or DEFAULT_CHAINS
    portfolios = []
    total_usd = 0.0

    for chain in targets:
        res = await get_wallet_token_balances(address=address, chain=chain)
        portfolios.append({
            "chain": chain,
            "token_count": res.get("token_count", 0),
            "total_usd_estimate": res.get("total_usd_estimate", 0),
            "top_tokens": res.get("tokens", [])[:10],
            "note": res.get("note"),
            "error": res.get("error"),
        })
        total_usd += float(res.get("total_usd_estimate", 0) or 0)

    eth_score = await score_wallet(address)
    tags = []
    if total_usd > 100000:
        tags.append("whale")
    if (eth_score.get("score") or 0) >= 70:
        tags.append("smart-money-candidate")
    if sum(p["token_count"] for p in portfolios) > 30:
        tags.append("diversified")

    return {
        "address": address,
        "chains": targets,
        "total_usd_estimate": round(total_usd, 2),
        "portfolios": portfolios,
        "ethereum_behavior_score": eth_score,
        "council_tags": tags,
        "council_summary": {
            "wallet_quality_score": eth_score.get("score"),
            "cross_chain_exposure_usd": round(total_usd, 2),
            "chains_active": len([p for p in portfolios if (p.get("total_usd_estimate") or 0) > 0]),
        },
    }

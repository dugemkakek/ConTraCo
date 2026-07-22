"""DEX Extended API — sniping, smart wallet tracking, tranche intelligence.

New endpoints added on top of the existing /api/v1/dex surface:

  DEX Sniping:
    GET /api/v1/dex/snipe/new-pools
    GET /api/v1/dex/snipe/trending
    GET /api/v1/dex/snipe/scan

  Smart Wallet Tracking:
    GET /api/v1/wallets/{address}/transactions
    GET /api/v1/wallets/{address}/tokens
    GET /api/v1/wallets/{address}/transfers/large
    GET /api/v1/wallets/{address}/score

  DEX Tranche Intelligence:
    GET /api/v1/dex/tranches/analyze
    GET /api/v1/dex/tranches/profitability
    GET /api/v1/dex/tranches/leaderboard
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.services.market_data.dex_sniping import (
    get_new_pools,
    get_trending_pools,
    multi_network_snipe_scan,
)
from app.services.onchain.wallet_tracker import (
    get_wallet_transactions,
    get_wallet_token_balances,
    get_large_token_transfers,
    score_wallet,
)
from app.services.market_data.tranche_intelligence import (
    analyze_pool_tranches,
    get_pool_position_profitability,
    tranche_leaderboard,
)

# ────────────────────────── DEX Sniping Router ──────────────────────────────

snipe_router = APIRouter(prefix="/api/v1/dex/snipe", tags=["dex-sniping"])


@snipe_router.get("/new-pools", summary="New pool launches")
async def new_pools(
    network: str = Query("ethereum", description="ethereum|base|polygon|arbitrum|optimism|bsc|solana"),
    minutes_back: int = Query(60, ge=5, le=1440, description="Look-back window in minutes"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Detect newly created liquidity pools on a DEX network."""
    res = await get_new_pools(network=network, minutes_back=minutes_back, limit=limit)
    if "error" in res and not res.get("pools"):
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@snipe_router.get("/trending", summary="Trending pools by 5-min volume")
async def trending_pools(
    network: str = Query("ethereum"),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    res = await get_trending_pools(network=network, limit=limit)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@snipe_router.get("/scan", summary="Multi-network parallel snipe scan")
async def snipe_scan(
    networks: str = Query("ethereum,base,arbitrum,polygon", description="Comma-separated network list"),
    minutes_back: int = Query(30, ge=5, le=240),
    min_liquidity_usd: float = Query(10_000, ge=0),
    max_rug_risk: float = Query(0.5, ge=0.0, le=1.0),
) -> dict:
    """Parallel scan for new launches across multiple networks with filtering."""
    net_list = [n.strip() for n in networks.split(",") if n.strip()]
    return await multi_network_snipe_scan(
        networks=net_list,
        minutes_back=minutes_back,
        min_liquidity_usd=min_liquidity_usd,
        max_rug_risk=max_rug_risk,
    )


# ─────────────────────── Smart Wallet Tracking Router ───────────────────────

wallet_router = APIRouter(prefix="/api/v1/wallets", tags=["wallet-tracking"])


@wallet_router.get("/{address}/transactions", summary="Wallet transaction history")
async def wallet_transactions(
    address: str,
    limit: int = Query(50, ge=1, le=200),
    chain: str = Query("ethereum"),
) -> dict:
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="address must be 0x-prefixed 20-byte hex")
    res = await get_wallet_transactions(address=address, limit=limit, chain=chain)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@wallet_router.get("/{address}/tokens", summary="ERC-20 token portfolio")
async def wallet_tokens(
    address: str,
    chain: str = Query("eth"),
) -> dict:
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="address must be 0x-prefixed 20-byte hex")
    return await get_wallet_token_balances(address=address, chain=chain)


@wallet_router.get("/{address}/transfers/large", summary="Large ERC-20 transfers (whale monitor)")
async def wallet_large_transfers(
    address: str,
    min_value_usd: float = Query(50_000, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="address must be 0x-prefixed 20-byte hex")
    res = await get_large_token_transfers(address=address, min_value_usd=min_value_usd, limit=limit)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@wallet_router.get("/{address}/score", summary="Smart wallet intelligence score (0-100)")
async def wallet_score(
    address: str,
) -> dict:
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="address must be 0x-prefixed 20-byte hex")
    res = await score_wallet(address=address)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


# ─────────────────────── DEX Tranche Intelligence Router ────────────────────

tranche_router = APIRouter(prefix="/api/v1/dex/tranches", tags=["dex-tranches"])


@tranche_router.get("/analyze", summary="Analyze pool tranches for LP opportunity")
async def analyze_tranches(
    network: str = Query("ethereum"),
    token_pair: Optional[str] = Query(None, description="e.g. ETH/USDC"),
    volatility: str = Query("medium", description="stable|low|medium|high"),
    limit: int = Query(30, ge=5, le=100),
) -> dict:
    res = await analyze_pool_tranches(
        network=network,
        token_pair=token_pair,
        volatility=volatility,
        limit=limit,
    )
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@tranche_router.get("/profitability", summary="LP position profitability estimate")
async def pool_profitability(
    pool_address: str = Query(..., description="0x-prefixed pool contract address"),
    network: str = Query("ethereum"),
    investment_usd: float = Query(10_000, ge=100),
    price_range_pct: float = Query(20.0, ge=1.0, le=200.0),
) -> dict:
    if not pool_address.startswith("0x") or len(pool_address) != 42:
        raise HTTPException(status_code=400, detail="pool_address must be 0x-prefixed 20-byte hex")
    res = await get_pool_position_profitability(
        pool_address=pool_address,
        network=network,
        investment_usd=investment_usd,
        price_range_pct=price_range_pct,
    )
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@tranche_router.get("/leaderboard", summary="Cross-network tranche leaderboard")
async def tranches_leaderboard(
    networks: str = Query("ethereum,base,arbitrum"),
    volatility: str = Query("medium"),
) -> dict:
    net_list = [n.strip() for n in networks.split(",") if n.strip()]
    return await tranche_leaderboard(networks=net_list, volatility=volatility)


__all__ = ["snipe_router", "wallet_router", "tranche_router"]

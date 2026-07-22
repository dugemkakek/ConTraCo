"""DEX integration HTTP surface.

Read-only endpoints that surface Uniswap v3 pools, Robinhood/base
tranches, and indicative swap quotes. Recommend-only — no transaction
construction, no signing, no wallet interaction.
"""

from fastapi import APIRouter, HTTPException, Query

from app.services.market_data import dex as dex_service
from app.services.market_data.free_sources import (
    collect_fundamentals,
    collect_macro,
    collect_sentiment,
    fetch_etherscan_exchange_flow,
    fetch_fear_and_greed,
    fetch_finnhub_calendar,
)
from app.services.market_data.free_sources import fetch_defillama_protocols as _fetch_llama_top

router = APIRouter(prefix="/api/v1/dex", tags=["dex"])


@router.get("/networks")
async def list_networks() -> dict:
    """Networks the DEX read path supports."""
    return {"networks": list(dex_service.SUPPORTED_NETWORKS)}


@router.get("/pools/top")
async def top_pools(
    network: str = Query("ethereum"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    res = await dex_service.list_top_pools(network=network, limit=limit)
    if "error" in res and "pools" not in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@router.get("/pools/{pool_address}")
async def pool_detail(pool_address: str, network: str = Query("ethereum")) -> dict:
    if not pool_address.startswith("0x") or len(pool_address) != 42:
        raise HTTPException(status_code=400, detail="pool_address must be 0x-prefixed 20-byte hex")
    res = await dex_service.get_pool(pool_address, network=network)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@router.get("/pools/range")
async def network_range(network: str = Query("ethereum")) -> dict:
    res = await dex_service.aggregate_network_state(network=network)
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@router.get("/tranches/robinhood-base")
async def robinhood_tranches() -> dict:
    """Discover tokenized-product pools on Base (Robinhood-style tranches)."""
    return await dex_service.discover_robinhood_tranches_on_base()


@router.get("/quote")
async def quote(
    token_in: str = Query(..., min_length=1),
    token_out: str = Query(..., min_length=1),
    amount_in: float = Query(..., gt=0),
    network: str = Query("ethereum"),
) -> dict:
    res = await dex_service.best_route_quote(
        token_in=token_in.upper(),
        token_out=token_out.upper(),
        amount_in=amount_in,
        network=network,
    )
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res


@router.get("/overview")
async def dex_overview() -> dict:
    """Cross-network DEX activity dashboard."""
    networks = list(dex_service.SUPPORTED_NETWORKS)
    out: dict = {"networks": []}
    for net in networks:
        agg = await dex_service.aggregate_network_state(network=net)
        out["networks"].append(agg)
    return out


# ---- Free-source router (fundamentals / macro / sentiment / calendar) -----

fundamentals_router = APIRouter(prefix="/api/v1/fundamentals/free", tags=["fundamentals"])


@fundamentals_router.get("/snapshot")
async def fundamentals_snapshot(symbol: str = Query(...)) -> dict:
    return await collect_fundamentals([symbol])


@fundamentals_router.get("/fear-and-greed")
async def fear_and_greed() -> dict:
    res = await fetch_fear_and_greed()
    if res.value is None:
        raise HTTPException(status_code=502, detail=res.error or "no data")
    return res.value


@fundamentals_router.get("/defillama/top")
async def defillama_top(limit: int = Query(25, ge=1, le=100)) -> dict:
    res = await _fetch_llama_top(top=limit)
    if res.value is None:
        raise HTTPException(status_code=502, detail=res.error or "no data")
    return res.value


@fundamentals_router.get("/calendar")
async def economic_calendar() -> dict:
    res = await fetch_finnhub_calendar()
    if res.value is None:
        raise HTTPException(status_code=503, detail=res.error or "finnhub unavailable")
    return res.value


@fundamentals_router.get("/on-chain/balance")
async def eth_balance(address: str = Query(...)) -> dict:
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="address must be 0x-prefixed 20-byte hex")
    res = await fetch_etherscan_exchange_flow(address=address)
    if res.value is None:
        raise HTTPException(status_code=502, detail=res.error or "etherscan unavailable")
    return res.value


sentiment_router = APIRouter(prefix="/api/v1/sentiment", tags=["sentiment"])


@sentiment_router.get("/{symbol:path}")
async def sentiment_for_symbol(symbol: str) -> dict:
    return await collect_sentiment(symbol)


macro_router = APIRouter(prefix="/api/v1/macro", tags=["macro"])


@macro_router.get("/snapshot")
async def macro_snapshot() -> dict:
    return await collect_macro()


__all__ = [
    "router",
    "fundamentals_router",
    "sentiment_router",
    "macro_router",
]

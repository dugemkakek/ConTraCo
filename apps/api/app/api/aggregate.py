"""Aggregate market overview — top-25 pairs by volume across all venues."""


import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.services.market_data.registry import all_providers, list_venues

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market", tags=["market"])


class TVPrefixMap(BaseModel):
    """Map venue IDs to TradingView exchange prefixes."""
    map: dict[str, str]


class TopPairOut(BaseModel):
    id: str
    base: str
    display: str
    venue: str
    volume_24h_quote: float
    price: float | None
    change_24h_pct: float | None


class AggregatedTopOut(BaseModel):
    timestamp: str
    top: list[TopPairOut]


# TV widget prefix per venue
TV_PREFIXES: dict[str, str] = {
    "gateio": "GATEIO",
    "binance": "BINANCE",
    "bybit": "BYBIT",
    "kraken": "KRAKEN",
    "okx": "OKX",
    "mock": "",
}


@router.get("/tv-prefixes", response_model=TVPrefixMap)
def tv_prefixes():
    """TradingView exchange prefix for each venue."""
    return TVPrefixMap(map=TV_PREFIXES)


@router.get("/top", response_model=AggregatedTopOut)
async def top_pairs(
    limit: int = Query(default=25, ge=1, le=100),
    min_volume: float = Query(default=0, ge=0),
    _user=Depends(get_current_user),
):
    """Top N pairs by 24h volume across all venues."""
    all_pairs: list[dict] = []
    for provider in all_providers():
        if hasattr(provider, "get_all_spot_pairs"):
            try:
                pairs = await provider.get_all_spot_pairs()
                all_pairs.extend(pairs)
            except Exception as exc:
                logger.warning("Failed to fetch pairs from %s: %s", provider.name, exc)

    # Deduplicate by base+venue (same base on diff venues are distinct)
    seen: set[str] = set()
    deduped = []
    for p in all_pairs:
        key = f"{p['base']}_{p['venue']}"
        if key not in seen and p["volume_24h_quote"] >= min_volume:
            seen.add(key)
            deduped.append(p)

    deduped.sort(key=lambda x: -x["volume_24h_quote"])
    top = [TopPairOut(**p) for p in deduped[:limit]]

    return AggregatedTopOut(
        timestamp=datetime.now(timezone.utc).isoformat(),
        top=top,
    )

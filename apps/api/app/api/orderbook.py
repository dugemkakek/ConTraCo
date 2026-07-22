"""Order book & market depth endpoints."""


import random
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import User
from app.db import redis_client
from app.services.market_data.snapshot import MarketSnapshotPipeline, SnapshotCache

router = APIRouter(prefix="/api/v1/market-data", tags=["orderbook"])


def _mock_orderbook(symbol: str, depth: int) -> dict:
    """Generate deterministic mock orderbook data."""
    base = {"BTC/USDT": 65000, "ETH/USDT": 3200, "SOL/USDT": 150}.get(symbol.upper(), 100)
    rng = random.Random(f"mock-ob-{symbol}")
    bids = []
    asks = []
    for i in range(depth):
        spread = base * random.Random(f"mock-spread-{symbol}-{i}").uniform(0.0001, 0.005)
        bid_price = round(base - spread * (i + 1), 2)
        ask_price = round(base + spread * (i + 1), 2)
        bid_size = round(rng.uniform(0.1, 5.0), 4)
        ask_size = round(rng.uniform(0.1, 5.0), 4)
        bids.append([bid_price, bid_size])
        asks.append([ask_price, ask_size])
    return {"bids": bids, "asks": asks, "provider": "mock"}


@router.get("/{symbol}/orderbook")
async def get_orderbook(
    symbol: str,
    depth: int = Query(default=20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """Fetch order book depth for a symbol."""
    from app.services.market_data.factory import build_provider
    provider = build_provider()
    if hasattr(provider, "get_order_book"):
        normalized = symbol.replace("-", "/").upper()
        snapshot = await MarketSnapshotPipeline(
            [provider], SnapshotCache(await redis_client.get_redis())
        ).build(
            normalized, "book", limit=depth, categories=("orderbook",)
        )
        if snapshot.order_book is None:
            return {"bids": [], "asks": [], "provider": provider.name, "note": "unavailable"}
        return {
            **snapshot.order_book,
            "provider": provider.name,
            "data_freshness": "STALE" if snapshot.stale_categories else "FRESH",
        }
    # Mock provider: return realistic fake orderbook
    return _mock_orderbook(symbol.replace("-", "/"), depth)
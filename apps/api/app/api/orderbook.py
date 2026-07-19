"""Order book & market depth endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter(prefix="/api/v1/market-data", tags=["orderbook"])


@router.get("/{symbol}/orderbook")
async def get_orderbook(
    symbol: str,
    depth: int = Query(default=20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """Fetch order book depth for a symbol."""
    from app.services.market_data.factory import build_provider
    from app.services.market_data.gateio_rest import GateioRestProvider
    provider = build_provider()
    if not isinstance(provider, GateioRestProvider):
        return {"bids": [], "asks": [], "provider": provider.name, "note": "mock/other provider"}
    normalized = symbol.replace("-", "/").upper()
    ob = await provider.get_order_book(normalized, depth)
    if ob is None:
        return {"bids": [], "asks": [], "provider": provider.name, "note": "unavailable"}
    return {**ob, "provider": provider.name}

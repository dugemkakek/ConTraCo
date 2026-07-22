"""Arbitrage API routes — yield opportunities and CEX/DEX spreads."""


from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models import User
from app.services.arbitrage.scanner import scan_cex_dex_spreads, scan_yield_opportunities

router = APIRouter(prefix="/api/v1/arbitrage", tags=["arbitrage"])


@router.get("/yield")
async def yield_opportunities(_user: Annotated[User, Depends(get_current_user)]):
    """Get delta-neutral yield opportunities across venues."""
    opps = await scan_yield_opportunities()
    return {"opportunities": opps, "count": len(opps)}


@router.get("/spreads")
async def cex_dex_spreads(_user: Annotated[User, Depends(get_current_user)]):
    """Get CEX vs DEX price disparities."""
    spreads = await scan_cex_dex_spreads()
    return {"spreads": spreads, "count": len(spreads)}
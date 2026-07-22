"""SEC EDGAR API routes — company filings and financials."""


from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import User
from app.services.fundamentals.sec_edgar import get_company_context, get_company_facts, search_filings

router = APIRouter(prefix="/api/v1/sec", tags=["sec"])


@router.get("/context")
async def sec_context(
    ticker: Annotated[str, Query(...)],
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Get structured SEC fundamental context for a ticker.

    Returns company facts (revenue, net income, EPS, assets) plus
    recent 10-K and 10-Q filings. Free, no API key.
    """
    return await get_company_context(ticker)


@router.get("/facts")
async def sec_facts(
    ticker: Annotated[str, Query(...)],
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Get raw SEC company facts (XBRL data)."""
    facts = await get_company_facts(ticker)
    if not facts:
        return {"available": False, "ticker": ticker, "reason": "not found or not SEC-registered"}
    return facts


@router.get("/filings")
async def sec_filings(
    ticker: Annotated[str, Query(...)],
    form_type: Annotated[str, Query(pattern="^(10-K|10-Q|8-K|DEF 14A)$")] = "10-K",
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Search recent SEC filings for a ticker."""
    filings = await search_filings(ticker, form_type=form_type, limit=limit)
    return {"ticker": ticker, "form_type": form_type, "filings": filings, "count": len(filings)}

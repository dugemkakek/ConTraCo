"""News & sentiment API routes."""


from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import User
from app.services.fundamentals.news_aggregator import get_news_context

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.get("/context")
async def news_context(
    symbol: Annotated[str, Query(...)],
    max_age_hours: Annotated[float, Query(ge=1, le=72)] = 12.0,
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Get news sentiment context for a symbol.

    Aggregates RSS feeds + Google News, matches by ticker,
    and runs VADER sentiment analysis.
    """
    return await get_news_context(symbol, max_age_hours=max_age_hours)

"""Fundamental intelligence routes — news, sentiment, calendar, on-chain."""


import logging
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import NewsItem, EconomicEvent, FundingRate, OnChainMetric, User
from app.services.fundamentals.news_aggregator import ingest_news
from app.services.fundamentals.context_builder import build_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fundamentals", tags=["fundamentals"])


class NewsItemOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    published_at: str | None
    symbol_relevance: list[str]
    sentiment_score: float | None
    summary: str | None
    created_at: str


class EconomicEventOut(BaseModel):
    id: int
    event_name: str
    country: str
    currency: str
    impact: str
    actual: float | None
    forecast: float | None
    previous: float | None
    event_time: str
    source_url: str | None


class FundingRateOut(BaseModel):
    id: int
    symbol: str
    venue: str
    rate: float
    timestamp: str


class OnChainMetricOut(BaseModel):
    id: int
    symbol: str
    metric_name: str
    value: float
    timestamp: str


class ContextOut(BaseModel):
    context: str
    as_of: str


def _row_to_dict(row) -> dict:
    """Convert SQLAlchemy model to dict with string datetimes."""
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            d[col.name] = val.isoformat()
        else:
            d[col.name] = val
    return d


@router.get("/news", response_model=list[NewsItemOut])
def list_news(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(NewsItem).where(NewsItem.created_at >= cutoff).order_by(desc(NewsItem.created_at)).limit(50)
    if symbol:
        stmt = stmt.where(NewsItem.symbol_relevance.any(symbol))
    return [_row_to_dict(r) for r in db.execute(stmt).scalars().all()]


@router.get("/calendar", response_model=list[EconomicEventOut])
def list_calendar(
    days: int = Query(default=7, ge=1, le=30),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    stmt = (
        select(EconomicEvent)
        .where(EconomicEvent.event_time >= now)
        .where(EconomicEvent.event_time <= cutoff)
        .order_by(EconomicEvent.event_time)
    )
    return [_row_to_dict(r) for r in db.execute(stmt).scalars().all()]


@router.get("/funding", response_model=list[FundingRateOut])
def list_funding(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(FundingRate).where(FundingRate.timestamp >= cutoff).order_by(desc(FundingRate.timestamp)).limit(50)
    if symbol:
        stmt = stmt.where(FundingRate.symbol == symbol)
    return [_row_to_dict(r) for r in db.execute(stmt).scalars().all()]


@router.get("/onchain", response_model=list[OnChainMetricOut])
def list_onchain(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(OnChainMetric).where(OnChainMetric.timestamp >= cutoff).order_by(desc(OnChainMetric.timestamp)).limit(50)
    if symbol:
        stmt = stmt.where(OnChainMetric.symbol == symbol)
    return [_row_to_dict(r) for r in db.execute(stmt).scalars().all()]


@router.get("/context", response_model=ContextOut)
async def get_context(
    symbol: str = Query(...),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ctx = await build_context(db, symbol)
    return ContextOut(context=ctx, as_of=datetime.now(timezone.utc).isoformat())


@router.post("/news/refresh")
def refresh_news(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ingest latest news from all sources."""
    import asyncio
    new_count = asyncio.run(ingest_news(db))
    return {"ingested": new_count}

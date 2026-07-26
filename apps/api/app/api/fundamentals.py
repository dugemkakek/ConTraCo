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


async def _live_funding_fallback(symbol: str | None, hours: int) -> list[dict]:
    """Live hourly funding series when the FundingRate table is empty.

    Delegates to the derivatives service (Hyperliquid primary, CoinGecko /
    Binance fapi fallbacks) and maps its ``{time, funding_rate, exchange}``
    rows onto the FundingRateOut shape. Synthesises a stable ``id`` per row
    (no DB primary key exists for live data) and clips to the ``hours``
    window the caller asked for.
    """
    from app.services.market_data.derivatives import get_funding_history

    sym = (symbol or "BTCUSDT").upper()
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)
    try:
        payload = await get_funding_history(sym, limit=max(hours, 24))
    except Exception:  # noqa: BLE001
        logger.exception("live funding fallback failed for %s", sym)
        return []
    out: list[dict] = []
    for i, r in enumerate(payload.get("rows") or []):
        t = r.get("time")
        if t is None or t < cutoff_ms:
            continue
        out.append({
            "id": i + 1,
            "symbol": payload.get("symbol", sym),
            "venue": r.get("exchange", payload.get("source", "unknown")),
            "rate": float(r.get("funding_rate", 0.0)),
            "timestamp": datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat(),
        })
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


@router.get("/news", response_model=list[NewsItemOut])
def list_news(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    # symbol_relevance is a JSON list column, not a PG ARRAY — filter in Python
    # (matches services/fundamentals/context_builder.py). Fetch a wider window,
    # then narrow + cap so a symbol filter still yields up to 50 matches.
    stmt = select(NewsItem).where(NewsItem.created_at >= cutoff).order_by(desc(NewsItem.created_at))
    stmt = stmt.limit(50 if not symbol else 500)
    rows = db.execute(stmt).scalars().all()
    if symbol:
        rows = [r for r in rows if symbol in (r.symbol_relevance or [])][:50]
    return [_row_to_dict(r) for r in rows]


@router.get("/calendar", response_model=list[EconomicEventOut])
async def list_calendar(
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
    rows = db.execute(stmt).scalars().all()
    if rows:
        return [_row_to_dict(r) for r in rows]
    # No stored events — serve the live ForexFactory (faireconomy mirror)
    # calendar so the endpoint returns real upcoming events, not a bare [].
    from app.services.fundamentals.macro_sources import get_economic_calendar

    return await get_economic_calendar(days)


@router.get("/funding", response_model=list[FundingRateOut])
async def list_funding(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(FundingRate).where(FundingRate.timestamp >= cutoff).order_by(desc(FundingRate.timestamp)).limit(50)
    if symbol:
        stmt = stmt.where(FundingRate.symbol == symbol)
    rows = db.execute(stmt).scalars().all()
    if rows:
        return [_row_to_dict(r) for r in rows]
    # No stored funding yet — serve a live hourly series so the endpoint is
    # never bare-empty. Hyperliquid (free, no key, reachable from geo-blocked
    # regions) is the primary source inside get_funding_history.
    return await _live_funding_fallback(symbol, hours)


@router.get("/onchain", response_model=list[OnChainMetricOut])
async def list_onchain(
    symbol: str | None = Query(None),
    hours: int = Query(default=24, ge=1, le=168),
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(OnChainMetric).where(OnChainMetric.timestamp >= cutoff).order_by(desc(OnChainMetric.timestamp)).limit(50)
    if symbol:
        stmt = stmt.where(OnChainMetric.symbol == symbol)
    rows = db.execute(stmt).scalars().all()
    if rows:
        return [_row_to_dict(r) for r in rows]
    # No stored metrics — serve live Bitcoin on-chain data from blockchain.info
    # (free, no key). Only BTC is available upstream; a non-BTC symbol filter
    # correctly yields an empty list.
    if symbol and symbol.upper() not in {"BTC", "BTCUSDT", "XBT"}:
        return []
    from app.services.fundamentals.macro_sources import get_onchain_metrics

    return await get_onchain_metrics(hours)


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

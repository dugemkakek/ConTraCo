"""Builds a structured fundamental context blob for LLM council injection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import NewsItem, EconomicEvent, FundingRate, OnChainMetric

logger = logging.getLogger(__name__)


async def build_context(db: Session, symbol: str) -> str:
    """Assemble a structured fundamental context string for the given symbol."""
    now = datetime.now(timezone.utc)
    lines: list[str] = []
    lines.append(f"FUNDAMENTAL CONTEXT for {symbol} (as of {now.strftime('%Y-%m-%d %H:%M UTC')}):")
    lines.append("")

    # 1. News sentiment (24h)
    cutoff = now - timedelta(hours=24)
    news = db.execute(
        select(NewsItem)
        .where(NewsItem.symbol_relevance.any(symbol))
        .where(NewsItem.created_at >= cutoff)
        .order_by(NewsItem.created_at.desc())
        .limit(20)
    ).scalars().all()

    if news:
        scores = [n.sentiment_score for n in news if n.sentiment_score is not None]
        avg_sentiment = sum(scores) / len(scores) if scores else None
        top = news[0]
        lines.append(f"- 24h News Sentiment: {f'{avg_sentiment:+.2f}' if avg_sentiment else 'N/A'} ({len(news)} articles)")
        lines.append(f"- Top Headline: \"{top.title[:120]}\" (sentiment: {top.sentiment_score or 'N/A'})")
    else:
        lines.append("- 24h News Sentiment: N/A (no news tracked)")

    # 2. Economic events (upcoming 7 days)
    events = db.execute(
        select(EconomicEvent)
        .where(EconomicEvent.event_time >= now)
        .where(EconomicEvent.event_time <= now + timedelta(days=7))
        .where(EconomicEvent.impact.in_(["high", "medium"]))
        .order_by(EconomicEvent.event_time)
        .limit(10)
    ).scalars().all()

    if events:
        for ev in events:
            warning = "⚠️" if ev.impact == "high" else "ℹ️"
            hours_until = int((ev.event_time - now).total_seconds() / 3600)
            lines.append(f"- {warning} {ev.event_name} ({ev.country}/{ev.currency}, {ev.impact.upper()}) "
                         f"in ~{hours_until}h — Forecast: {ev.forecast or 'N/A'}, Prev: {ev.previous or 'N/A'}")

    # 3. Funding rates (latest per venue)
    rates = db.execute(
        select(FundingRate)
        .where(FundingRate.symbol == symbol)
        .where(FundingRate.timestamp >= now - timedelta(hours=2))
        .order_by(FundingRate.timestamp.desc())
        .limit(3)
    ).scalars().all()
    if rates:
        for r in rates[:1]:
            flag = "" if abs(r.rate) < 0.001 else " ⚠️ EXTREME"
            lines.append(f"- Funding Rate ({r.venue}): {r.rate:+.4%}{flag}")
    else:
        lines.append("- Funding Rate: N/A")

    # 4. On-chain metrics (latest per metric type)
    metrics = db.execute(
        select(OnChainMetric)
        .where(OnChainMetric.symbol == symbol)
        .where(OnChainMetric.timestamp >= now - timedelta(days=1))
        .order_by(OnChainMetric.timestamp.desc())
        .limit(5)
    ).scalars().all()
    seen_metrics: set[str] = set()
    for m in metrics:
        if m.metric_name not in seen_metrics:
            seen_metrics.add(m.metric_name)
            lines.append(f"- {m.metric_name}: {m.value}")

    # 5. Risk flags
    risk_flags: list[str] = []
    for ev in events:
        hours_until = int((ev.event_time - now).total_seconds() / 3600)
        if ev.impact == "high" and hours_until <= 2:
            risk_flags.append(f"High-impact economic event ({ev.event_name}) in {hours_until}h — reduce position size")

    for r in rates:
        if abs(r.rate) > 0.001:
            risk_flags.append(f"Extreme funding rate ({r.rate:+.4%} on {r.venue}) — potential liquidation cascade")

    if risk_flags:
        for rf in risk_flags:
            lines.append(f"- RISK FLAG: {rf}")

    return "\n".join(lines)

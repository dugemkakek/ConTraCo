"""News aggregator — collect, tag by ticker, and score sentiment.

Combines RSS feeds + Google News search into a unified pipeline
that produces per-symbol fundamental context for the gate engine.
Also provides `ingest_news(db)` to persist items into the NewsItem table.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.fundamentals.rss_poller import NewsItem as RssNewsItem, fetch_all_feeds, google_news_rss
from app.services.fundamentals.sentiment import aggregate_sentiment, analyze_sentiment

logger = logging.getLogger(__name__)

# Ticker/symbol patterns for matching news to symbols
TICKER_PATTERNS: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc", "satoshi", "lightning network"],
    "ETH": ["ethereum", "eth", "vitalik", "erc-20", "eip"],
    "SOL": ["solana", "sol", "phantom wallet"],
    "BNB": ["bnb", "binance coin", "binance chain"],
    "XRP": ["xrp", "ripple", "sec lawsuit"],
    "ADA": ["cardano", "ada", "charles hoskinson"],
    "AVAX": ["avalanche", "avax"],
    "DOGE": ["dogecoin", "doge", "elon"],
    "DOT": ["polkadot", "dot", "gavin wood"],
    "LINK": ["chainlink", "link", "oracle"],
    "MATIC": ["polygon", "matic"],
    "ARB": ["arbitrum", "arb"],
    "OP": ["optimism", "op stack"],
    "ATOM": ["cosmos", "atom", "ibc"],
    "UNI": ["uniswap", "uni"],
    "AAVE": ["aave"],
    "SPY": ["s&p 500", "spy", "stock market", "wall street"],
    "QQQ": ["nasdaq", "qqq", "tech stocks"],
}

# Macro keywords that affect all markets
MACRO_KEYWORDS = [
    "federal reserve", "fed rate", "interest rate", "inflation", "cpi",
    "gdp", "unemployment", "treasury", "yield curve", "recession",
    "tariff", "trade war", "geopolitical", "sanctions",
]


def match_tickers(text: str) -> list[str]:
    """Find which tickers/symbols a text mentions."""
    text_lower = text.lower()
    matched = []
    for ticker, patterns in TICKER_PATTERNS.items():
        if any(p in text_lower for p in patterns):
            matched.append(ticker)
    return matched


def is_macro_relevant(text: str) -> bool:
    """Check if text contains macro-economic keywords."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in MACRO_KEYWORDS)


async def get_news_context(
    symbol: str,
    max_age_hours: float = 12.0,
    max_items: int = 30,
) -> dict[str, Any]:
    """Build fundamental news context for a symbol.

    Returns:
      - sentiment: aggregated VADER sentiment for matched articles
      - macro_sentiment: sentiment for macro-relevant articles
      - articles: list of matched article summaries
      - total_scanned: total articles scanned
      - source: data source identifier
    """
    base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()

    # 1. Fetch all niche feeds
    all_news = await fetch_all_feeds(max_age_hours=max_age_hours)

    # 2. Also search Google News for the specific ticker
    try:
        ticker_news = await google_news_rss(base, max_results=10)
        all_news.extend(ticker_news)
    except Exception:
        pass

    # 3. Filter to articles mentioning this ticker or macro
    matched: list[RssNewsItem] = []
    macro_articles: list[RssNewsItem] = []

    for item in all_news:
        text = f"{item.title} {item.summary}"
        tickers = match_tickers(text)
        if base in tickers:
            matched.append(item)
        if is_macro_relevant(text):
            macro_articles.append(item)

    # Deduplicate by title similarity
    seen_titles: set[str] = set()
    unique_matched: list[RssNewsItem] = []
    for item in matched:
        key = item.title.lower().strip()[:60]
        if key not in seen_titles:
            seen_titles.add(key)
            unique_matched.append(item)
    unique_matched = unique_matched[:max_items]

    # 4. Sentiment analysis
    matched_texts = [f"{a.title}. {a.summary}" for a in unique_matched]
    macro_texts = [f"{a.title}. {a.summary}" for a in macro_articles[:20]]

    sentiment = aggregate_sentiment(matched_texts)
    macro_sentiment = aggregate_sentiment(macro_texts)

    return {
        "symbol": symbol,
        "sentiment": sentiment,
        "macro_sentiment": macro_sentiment,
        "articles": [
            {
                "title": a.title,
                "source": a.source,
                "published": a.published,
                "link": a.link,
                "tags": a.tags,
            }
            for a in unique_matched[:10]
        ],
        "total_scanned": len(all_news),
        "matched_count": len(unique_matched),
        "macro_count": len(macro_articles),
        "source": "rss+google_news+vader",
    }


async def ingest_news(db: Session) -> int:
    """Fetch RSS feeds, match tickers, score sentiment, persist to DB.

    Returns the number of newly inserted rows.
    """
    from app.db.models import NewsItem as NewsItemRow

    all_news = await fetch_all_feeds(max_age_hours=24.0)
    new_count = 0

    for item in all_news:
        text = f"{item.title} {item.summary}"
        tickers = match_tickers(text)
        if not tickers and not is_macro_relevant(text):
            continue

        # Skip duplicates (unique URL constraint)
        existing = db.query(NewsItemRow).filter(NewsItemRow.url == item.link).first()
        if existing:
            continue

        scores = analyze_sentiment(text)
        pub_dt = datetime.fromtimestamp(item.published, tz=timezone.utc) if item.published else None

        row = NewsItemRow(
            source=item.source,
            title=item.title[:500],
            url=item.link[:1000],
            published_at=pub_dt,
            symbol_relevance=tickers,
            sentiment_score=scores.get("compound"),
            summary=item.summary[:2000] if item.summary else None,
        )
        db.add(row)
        new_count += 1

    if new_count:
        db.commit()
    return new_count

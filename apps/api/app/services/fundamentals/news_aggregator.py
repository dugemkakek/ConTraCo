"""News aggregation from RSS, NewsAPI, and CryptoPanic."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NewsItem

logger = logging.getLogger(__name__)

# RSS feeds for crypto news
RSS_FEEDS = [
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://cryptoslate.com/feed/",
]

# Symbol keyword mapping for tagging
SYMBOL_KEYWORDS: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc", "#btc"],
    "ETH": ["ethereum", "eth", "#eth"],
    "SOL": ["solana", "sol", "#sol"],
    "BNB": ["binance coin", "bnb", "#bnb"],
    "XRP": ["ripple", "xrp", "#xrp"],
    "ADA": ["cardano", "ada", "#ada"],
    "AVAX": ["avalanche", "avax", "#avax"],
}


def _tag_symbols(title: str, summary: str | None) -> list[str]:
    """Tag article with relevant symbols using keyword matching."""
    text = (title + " " + (summary or "")).lower()
    matched = []
    for symbol, keywords in SYMBOL_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(f"{symbol}/USDT")
    return matched


def _dedup_key(item: dict[str, Any]) -> str:
    """Generate a unique hash for deduplication."""
    raw = item.get("title", "") + item.get("link", "")
    return hashlib.md5(raw.encode()).hexdigest()


async def fetch_news() -> list[dict[str, Any]]:
    """Fetch news from all sources. Returns list of normalized articles."""
    articles: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for feed_url in RSS_FEEDS:
            try:
                resp = await client.get(feed_url, headers={"User-Agent": "confluence-trading-consultant/1.0"})
                if resp.status_code != 200:
                    logger.warning("RSS %s returned %d", feed_url, resp.status_code)
                    continue
                # Basic XML parsing — extract title, link, pubDate
                raw = resp.text
                # Simple extraction (full XML parser would be feedparser; this is minimal)
                import re
                titles = re.findall(r"<title[^>]*>(.*?)</title>", raw, re.DOTALL)
                links = re.findall(r"<link[^>]*>(.*?)</link>", raw, re.DOTALL)
                pub_dates = re.findall(r"<pubDate[^>]*>(.*?)</pubDate>", raw, re.DOTALL)

                for i, title in enumerate(titles):
                    if not title or title.startswith("<!") or title.startswith("[CDATA["):
                        continue
                    articles.append({
                        "source": feed_url.split("/")[2],
                        "title": title.strip(),
                        "link": links[i] if i < len(links) else "",
                        "published_at": pub_dates[i] if i < len(pub_dates) else None,
                    })
            except Exception as exc:  # noqa: BLE001
                logger.debug("RSS fetch failed for %s: %s", feed_url, exc)

    return articles


async def ingest_news(db: Session) -> int:
    """Fetch news, deduplicate, tag symbols, store in DB. Returns new count."""
    articles = await fetch_news()
    seen = set()
    new_count = 0

    for article in articles:
        key = _dedup_key(article)
        if key in seen:
            continue
        seen.add(key)

        # Check if already in DB
        url = article.get("link", "")
        existing = db.execute(select(NewsItem).where(NewsItem.url == url)).scalar_one_or_none()
        if existing:
            continue

        title = article.get("title", "")[:500]
        symbols = _tag_symbols(title, None)
        published = None
        if article.get("published_at"):
            try:
                from email.utils import parsedate_to_datetime
                published = parsedate_to_datetime(article["published_at"])
            except Exception:  # noqa: BLE001
                pass

        item = NewsItem(
            source=article.get("source", "unknown")[:50],
            title=title,
            url=url[:1000],
            published_at=published,
            symbol_relevance=symbols,
            sentiment_score=None,
            summary=None,
        )
        db.add(item)
        new_count += 1

    if new_count:
        db.commit()
        logger.info("Ingested %d new news items", new_count)

    return new_count

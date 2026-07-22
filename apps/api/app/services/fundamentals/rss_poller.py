"""RSS feed poller — fetch and parse RSS/Atom feeds for financial news.

Free feeds, no API key:
  - CoinDesk, The Block, Decrypt (crypto)
  - Yahoo Finance, MarketWatch (equities)
  - Reuters, AP (macro/politics)
  - Google News RSS (keyword search)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import feedparser
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "confluence-trading-consultant/1.0"
TIMEOUT = 10.0

# Curated free RSS feeds by niche
FEEDS: dict[str, list[str]] = {
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.theblock.co/rss.xml",
        "https://decrypt.co/feed",
        "https://cointelegraph.com/rss",
    ],
    "equities": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "https://www.marketwatch.com/rss/topstories",
    ],
    "macro": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://rsshub.app/apnews/topics/apf-topnews",
        "https://www.theguardian.com/world/rss",
    ],
    "tech": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
    ],
}


@dataclass
class NewsItem:
    title: str
    link: str
    summary: str
    published: float  # unix timestamp
    source: str
    feed_url: str
    tags: list[str] = field(default_factory=list)


async def fetch_feed(url: str, source: str) -> list[NewsItem]:
    """Fetch and parse a single RSS/Atom feed."""
    items: list[NewsItem] = []
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return items
            parsed = feedparser.parse(resp.text)
    except Exception as exc:
        logger.debug("RSS fetch failed for %s: %s", url, exc)
        return items

    for entry in parsed.entries[:20]:  # cap per feed
        published = time.mktime(entry.published_parsed) if entry.get("published_parsed") else time.time()
        items.append(NewsItem(
            title=entry.get("title", "").strip(),
            link=entry.get("link", ""),
            summary=(entry.get("summary", "") or "")[:500],
            published=published,
            source=source,
            feed_url=url,
        ))
    return items


async def fetch_all_feeds(
    niches: list[str] | None = None,
    max_age_hours: float = 24.0,
) -> list[NewsItem]:
    """Fetch all feeds for the given niches (default: all).

    Returns items sorted by published desc, filtered to max_age_hours.
    """
    if niches is None:
        niches = list(FEEDS.keys())

    cutoff = time.time() - (max_age_hours * 3600)
    all_items: list[NewsItem] = []

    for niche in niches:
        urls = FEEDS.get(niche, [])
        for url in urls:
            source = url.split("/")[2] if "//" in url else url
            items = await fetch_feed(url, source)
            for item in items:
                item.tags.append(niche)
                if item.published >= cutoff:
                    all_items.append(item)

    all_items.sort(key=lambda x: -x.published)
    return all_items


async def google_news_rss(query: str, max_results: int = 15) -> list[NewsItem]:
    """Search Google News RSS for a keyword query (free, no key)."""
    import urllib.parse
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    items = await fetch_feed(url, "google_news")
    return items[:max_results]

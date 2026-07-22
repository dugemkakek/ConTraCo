"""Free-tier public-data provider aggregator.

Catalog of read-only providers (no execution, no keys required for the
default tier) wired into the MarketSnapshot pipeline. Every method
returns a neutral ``(value, error)`` shape — gates that consume them
fall back to ``insufficient data`` rather than crashing if the upstream
goes away. Rate-limit budgets live in :mod:`app.services.market_data.snapshot`.

Source list (locked at v1):
  * CoinGecko — market cap, dominance, OHLCV (no key, demo-lift via env)
  * DeFiLlama — TVL, protocol metrics (no key)
  * alternative.me — Fear & Greed Index (no key)
  * Frankfurter — ECB reference FX rates, free (no key)
  * FRED — official US macro (env: FRED_API_KEY)
  * The Graph free-tier subgraphs — DEX pool data (no key)
  * StockTwits — sentiment with built-in bull/bear label (no key)
  * Finnhub — calendar + news (env: FINNHUB_API_KEY)
  * NewsAPI / Google News RSS — generic news
  * Etherscan — on-chain (env: ETHERSCAN_API_KEY)

Every provider raises ``ProviderError`` on failure so the snapshot
pipeline's failover chain can move to the next provider cleanly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "8.0"))
USER_AGENT = "confluence-trading-consultant/1.0 (recommend-only)"


def _ssl_setting() -> bool:
    """Verification is on unless explicitly disabled via env (corporate MITM
    networks). Default safe behaviour preserves TLS verification."""
    return os.getenv("FREE_PROVIDER_VERIFY_SSL", "1") == "1"


class ProviderError(RuntimeError):
    """Raised by free-source providers on any failure mode."""


@dataclass
class ProviderResult:
    value: Any
    error: str | None = None


def _get(d: dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


async def _get_json(url: str, *, params: dict[str, Any] | None = None,
                    headers: dict[str, str] | None = None) -> ProviderResult:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
            resp = await client.get(url, params=params or {}, headers=headers)
            if resp.status_code == 429:
                return ProviderResult(None, f"rate-limited ({resp.status_code})")
            if resp.status_code >= 400:
                return ProviderResult(None, f"http {resp.status_code}")
            return ProviderResult(resp.json())
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(None, str(exc))


# --------------------------------------------------------------------- CoinGecko

async def fetch_coingecko_global() -> ProviderResult:
    """BTC dominance + total market cap. No key needed for the public endpoint."""
    res = await _get_json("https://api.coingecko.com/api/v3/global")
    if res.error or not isinstance(res.value, dict):
        return res
    data = _get(res.value, "data", "market_cap_percentage", default={}) or {}
    total_mcap = _get(res.value, "data", "total_market_cap", "usd")
    return ProviderResult({
        "btc_dominance_pct": data.get("btc"),
        "eth_dominance_pct": data.get("eth"),
        "total_market_cap_usd": total_mcap,
    })


async def fetch_coingecko_simple_price(symbols: list[str]) -> ProviderResult:
    """Map exchange symbols (BTC/USDT) to CoinGecko ids; returns USD price."""
    id_map = {
        "BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "SOL/USDT": "solana",
        "BNB/USDT": "binancecoin", "XRP/USDT": "ripple", "ADA/USDT": "cardano",
        "DOGE/USDT": "dogecoin", "MATIC/USDT": "matic-network", "AVAX/USDT": "avalanche-2",
        "LINK/USDT": "chainlink", "DOT/USDT": "polkadot", "TRX/USDT": "tron",
    }
    cg_ids = [id_map[s] for s in symbols if s in id_map]
    if not cg_ids:
        return ProviderResult({}, "unknown symbols")
    res = await _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(cg_ids), "vs_currencies": "usd",
                "include_24hr_change": "true", "include_market_cap": "true"},
    )
    if res.error:
        return res
    prices: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        cg_id = id_map.get(sym)
        if not cg_id:
            continue
        row = res.value.get(cg_id, {})
        prices[sym] = {
            "usd": row.get("usd"),
            "change_24h_pct": row.get("usd_24h_change"),
            "market_cap_usd": row.get("usd_market_cap"),
        }
    return ProviderResult({"prices": prices})


# ---------------------------------------------------------------------- DeFiLlama

async def fetch_defillama_protocols(top: int = 25) -> ProviderResult:
    res = await _get_json("https://api.llama.fi/protocols")
    if res.error or not isinstance(res.value, list):
        return res
    ranked = sorted(
        [p for p in res.value if isinstance(p.get("tvl"), (int, float))],
        key=lambda p: float(p.get("tvl", 0) or 0),
        reverse=True,
    )[:top]
    return ProviderResult({
        "protocols": [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "chain": p.get("chain"),
                "tvl_usd": p.get("tvl"),
                "change_1d_pct": p.get("change_1d"),
                "change_7d_pct": p.get("change_7d"),
                "slug": p.get("slug"),
            }
            for p in ranked
        ]
    })


async def fetch_defillama_global_tvl() -> ProviderResult:
    res = await _get_json("https://api.llama.fi/v2/chains")
    if res.error or not isinstance(res.value, list):
        return res
    return ProviderResult({
        "chains": [
            {"name": c.get("name"), "tvl_usd": c.get("tvl")}
            for c in res.value[:20] if isinstance(c.get("tvl"), (int, float))
        ]
    })


# ----------------------------------------------------------------- alternative.me

async def fetch_fear_and_greed() -> ProviderResult:
    res = await _get_json("https://api.alternative.me/fng/")
    if res.error:
        return res
    data = (res.value or {}).get("data") or []
    if not data:
        return ProviderResult(None, "empty payload")
    head = data[0]
    try:
        return ProviderResult({
            "value": int(head.get("value", 0)),
            "classification": head.get("value_classification"),
            "timestamp": head.get("timestamp"),
        })
    except (ValueError, TypeError):
        return ProviderResult(None, "invalid payload")


# ------------------------------------------------------------------- Frankfurter

async def fetch_fx_reference(base: str = "USD") -> ProviderResult:
    res = await _get_json(f"https://api.frankfurter.dev/v1/latest",
                          params={"base": base})
    if res.error:
        return res
    return ProviderResult(res.value or {})


# ---------------------------------------------------------------------- FRED

async def fetch_fred_macro(series_ids: list[str] | None = None) -> ProviderResult:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return ProviderResult(None, "FRED_API_KEY not set")
    series_ids = series_ids or [
        "DGS10", "DGS2", "T10Y2Y", "CPIAUCSL", "UNRATE", "FEDFUNDS",
    ]
    rows: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
        for sid in series_ids:
            try:
                resp = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={"series_id": sid, "api_key": api_key,
                            "file_type": "json", "limit": 5,
                            "sort_order": "desc"},
                    headers={"User-Agent": USER_AGENT},
                )
                if resp.status_code >= 400:
                    continue
                observations = (resp.json() or {}).get("observations") or []
                if observations:
                    rows[sid] = observations[0]
            except Exception as exc:  # noqa: BLE001
                logger.debug("FRED %s failed: %s", sid, exc)
    if not rows:
        return ProviderResult(None, "all FRED series failed")
    return ProviderResult({"series": rows})


# ------------------------------------------------------------------- StockTwits

async def fetch_stocktwits_symbol(symbol: str) -> ProviderResult:
    clean = symbol.replace("/", "").upper()
    res = await _get_json(f"https://api.stocktwits.com/api/2/streams/symbol/{clean}.json")
    if res.error:
        return res
    msgs = (res.value or {}).get("messages") or []
    if not msgs:
        return ProviderResult({"bullish": 0, "bearish": 0, "neutral": 0, "volume": 0})
    bull = bear = 0
    for m in msgs:
        sentiment = (m.get("entities") or {}).get("sentiment") or {}
        basic = sentiment.get("basic")
        if basic == "Bullish":
            bull += 1
        elif basic == "Bearish":
            bear += 1
    return ProviderResult({
        "bullish": bull,
        "bearish": bear,
        "neutral": len(msgs) - bull - bear,
        "volume": len(msgs),
        "watchers": (res.value or {}).get("symbol", {}).get("watchlist_count"),
    })


# -------------------------------------------------------------------- Finnhub

async def fetch_finnhub_calendar(category: str = "all") -> ProviderResult:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return ProviderResult(None, "FINNHUB_API_KEY not set")
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
        try:
            resp = await client.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"token": api_key, "from": today, "to": today},
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code >= 400:
                return ProviderResult(None, f"finnhub {resp.status_code}")
            return ProviderResult({"economic": (resp.json() or {}).get("economicCalendar", [])[:30]})
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(None, str(exc))


async def fetch_finnhub_news(symbol: str) -> ProviderResult:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return ProviderResult(None, "FINNHUB_API_KEY not set")
    clean = symbol.replace("/", "").upper().replace("USDT", "").replace("USD", "")
    from datetime import datetime, timedelta, timezone
    frm = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
        try:
            resp = await client.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": clean, "from": frm, "to": to, "token": api_key},
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code >= 400:
                return ProviderResult(None, f"finnhub {resp.status_code}")
            return ProviderResult({"news": (resp.json() or [])[:30]})
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(None, str(exc))


# --------------------------------------------------------------- Google News RSS

# ---- Curated RSS feeds (no key) ------

CURATED_RSS_FEEDS: dict[str, str] = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "theblock": "https://www.theblock.co/rss.xml",
    "decrypt": "https://decrypt.co/feed",
    "bitcoin_magazine": "https://bitcoinmagazine.com/.rss/full/",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "reuters_markets": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "cnbc_top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "wsj_markets": "https://feeds.a.dj.wsj.com/rss/RSSMarketsMain.xml",
    "marketwatch_pulse": "http://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "investing_forex": "https://www.investing.com/rss/news_25.rss",
    "google_news_btc": "https://news.google.com/rss/search?q=bitcoin&hl=en-US&gl=US&ceid=US:en",
    "google_news_eth": "https://news.google.com/rss/search?q=ethereum&hl=en-US&gl=US&ceid=US:en",
    "forexfactory_calendar": "https://www.forexfactory.com/calendar?feed=rss",
}


async def fetch_rss(name: str, limit: int = 30) -> ProviderResult:
    import feedparser
    url = CURATED_RSS_FEEDS.get(name)
    if not url:
        return ProviderResult(None, f"unknown feed: {name}")
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                return ProviderResult(None, f"rss {resp.status_code}")
            parsed = feedparser.parse(resp.text)
            entries = []
            for e in parsed.entries[:limit]:
                entries.append({
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "published": getattr(e, "published", ""),
                    "summary": getattr(e, "summary", ""),
                    "author": getattr(e, "author", ""),
                    "tags": list(getattr(e, "tags", []))[:3] if getattr(e, "tags", None) else [],
                    "source": name,
                })
            return ProviderResult({"feed": name, "entries": entries, "count": len(entries)})
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(None, str(exc))


async def fetch_all_news_rss(symbol: str | None = None, limit_per_feed: int = 8) -> dict[str, Any]:
    """Fan-out all feeds in parallel; aggregate."""
    out: dict[str, Any] = {"feeds": {}, "merged": []}
    feeds = list(CURATED_RSS_FEEDS.keys())
    if symbol:
        feeds = [name for name in feeds
                 if name not in ("google_news_btc", "google_news_eth")] + [
            f"google_news_{symbol.lower().split('/')[0]}"
        ]
    async def _gather(name: str) -> None:
        res = await fetch_rss(name, limit=limit_per_feed)
        if res.value:
            out["feeds"][name] = res.value
            for entry in res.value.get("entries", []):
                out["merged"].append({**entry, "feed": name})
        else:
            out["feeds"][name] = {"error": res.error}

    await asyncio.gather(*(_gather(name) for name in feeds))
    # Dedupe by link
    seen: set[str] = set()
    deduped = []
    for e in out["merged"]:
        link = e.get("link") or e.get("title", "")
        if link in seen:
            continue
        seen.add(link)
        deduped.append(e)
    out["merged"] = deduped
    out["total_count"] = len(deduped)
    return out


# -------------------------------------------- Reddit & social aggregation ---

REDDIT_SUBREDDITS: dict[str, str] = {
    "cryptocurrency": "https://www.reddit.com/r/CryptoCurrency/hot.json?limit=25",
    "bitcoin": "https://www.reddit.com/r/Bitcoin/hot.json?limit=25",
    "ethereum": "https://www.reddit.com/r/ethereum/hot.json?limit=25",
    "ethfinance": "https://www.reddit.com/r/ethfinance/hot.json?limit=25",
    "defi": "https://www.reddit.com/r/defi/hot.json?limit=25",
    "wallstreetbets": "https://www.reddit.com/r/wallstreetbets/hot.json?limit=25",
    "stocks": "https://www.reddit.com/r/stocks/hot.json?limit=25",
    "algotrading": "https://www.reddit.com/r/algotrading/hot.json?limit=25",
}


async def fetch_reddit(subreddit: str, limit: int = 25) -> ProviderResult:
    url = REDDIT_SUBREDDITS.get(subreddit)
    if not url:
        return ProviderResult(None, f"unknown subreddit: {subreddit}")
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            if resp.status_code != 200:
                return ProviderResult(None, f"reddit {resp.status_code}")
            data = (resp.json() or {}).get("data", {}).get("children", [])
            entries = []
            for child in data[:limit]:
                row = (child or {}).get("data") or {}
                entries.append({
                    "title": row.get("title", ""),
                    "url": row.get("url_overridden_by_dest") or row.get("url", ""),
                    "permalink": f"https://reddit.com{row.get('permalink', '')}",
                    "score": row.get("score", 0),
                    "num_comments": row.get("num_comments", 0),
                    "subreddit": row.get("subreddit", subreddit),
                    "created_utc": row.get("created_utc", 0),
                    "selftext": (row.get("selftext") or "")[:280],
                })
            return ProviderResult({"subreddit": subreddit, "entries": entries, "count": len(entries)})
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(None, str(exc))


async def fetch_all_reddit() -> dict[str, Any]:
    out: dict[str, Any] = {"feeds": {}, "merged": []}
    seen: set[str] = set()

    async def _gather(name: str) -> None:
        res = await fetch_reddit(name)
        if res.value:
            out["feeds"][name] = res.value
            for entry in res.value.get("entries", []):
                key = entry.get("permalink") or entry.get("title")
                if key in seen:
                    continue
                seen.add(key)
                out["merged"].append(entry)
        else:
            out["feeds"][name] = {"error": res.error}

    await asyncio.gather(*(_gather(name) for name in REDDIT_SUBREDDITS))
    out["merged"].sort(key=lambda e: -e.get("score", 0))
    return out


async def fetch_google_news_rss(query: str, limit: int = 30) -> ProviderResult:
    import feedparser  # local import — only used when RSS path is hot
    from urllib.parse import quote_plus
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "+when:1d&hl=en-US&gl=US&ceid=US:en")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                return ProviderResult(None, f"rss {resp.status_code}")
            parsed = feedparser.parse(resp.text)
            entries = [
                {"title": e.title, "link": e.link, "published": e.get("published")}
                for e in parsed.entries[:limit]
            ]
            return ProviderResult({"news": entries})
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(None, str(exc))


# ------------------------------------------------------------ DEX via The Graph

UNISWAP_V3_SUBGRAPH = (
    "https://gateway.thegraph.com/api/{key}/subgraphs/id/" +
    "5zvR82QoaXYVafVWfbTx8L63NG8EPet7hp8bhnyfqtk3"
)
UNISWAP_V3_PUBLIC = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"


def _decode_subgraph_response(resp: httpx.Response) -> dict[str, Any] | None:
    """The free path may return HTML/empty when queries fail; JSON-decode safely."""
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        return None


async def fetch_uniswap_v3_pool(pool_address: str, network: str = "ethereum") -> ProviderResult:
    """Top pool price + 24h volume from the Uniswap v3 subgraph."""
    if network not in {"ethereum", "polygon", "arbitrum", "optimism", "base"}:
        return ProviderResult(None, f"unsupported network {network}")
    query = """
    query($pool: String!) {
      pool(id: $pool) {
        token0 { symbol decimals }
        token1 { symbol decimals }
        token0Price
        token1Price
        volumeUSD24h
        liquidity
        tick
        sqrtPrice
        feeTier
      }
    }"""
    api_key = os.getenv("GRAPH_API_KEY")
    url = UNISWAP_V3_SUBGRAPH.format(key=api_key) if api_key else UNISWAP_V3_PUBLIC
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
            resp = await client.post(url, json={"query": query, "variables": {"pool": pool_address.lower()}},
                                     headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                return ProviderResult(None, f"thegraph {resp.status_code}")
            data = _decode_subgraph_response(resp)
            if data is None:
                return ProviderResult(None, "non-JSON subgraph response")
            pool = (data.get("data", {}).get("pool") or {})
            if not pool:
                return ProviderResult(None, "pool not found")
            return ProviderResult({
                "pool_address": pool_address,
                "network": network,
                "token0": pool["token0"]["symbol"],
                "token1": pool["token1"]["symbol"],
                "token0_price": float(pool["token0Price"]),
                "token1_price": float(pool["token1Price"]),
                "volume_24h_usd": float(pool["volumeUSD24h"] or 0),
                "liquidity_usd": float(pool["liquidity"] or 0),
                "tick": int(pool["tick"] or 0),
                "fee_tier": int(pool["feeTier"] or 0),
            })
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(None, str(exc))


async def fetch_top_uniswap_pools(network: str = "ethereum", limit: int = 20) -> ProviderResult:
    if network not in {"ethereum", "polygon", "arbitrum", "optimism", "base"}:
        return ProviderResult(None, f"unsupported network {network}")
    query = """
    query($first: Int!) {
      pools(first: $first, orderBy: totalValueLockedUSD, orderDirection: desc) {
        id
        token0 { symbol }
        token1 { symbol }
        token0Price
        token1Price
        volumeUSD24h
        liquidity
        feeTier
      }
    }"""
    api_key = os.getenv("GRAPH_API_KEY")
    url = UNISWAP_V3_SUBGRAPH.format(key=api_key) if api_key else UNISWAP_V3_PUBLIC
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
            resp = await client.post(url, json={"query": query, "variables": {"first": limit}},
                                     headers={"User-Agent": USER_AGENT})
            if resp.status_code >= 400:
                return ProviderResult(None, f"thegraph {resp.status_code}")
            data = _decode_subgraph_response(resp)
            if data is None:
                return ProviderResult(None, "non-JSON subgraph response")
            rows = (data.get("data", {}).get("pools", []) or [])
            return ProviderResult({
                "network": network,
                "pools": [
                    {"address": p["id"], "base": p["token0"]["symbol"],
                     "quote": p["token1"]["symbol"],
                     "price": float(p["token0Price"]),
                     "volume_24h_usd": float(p["volumeUSD24h"] or 0),
                     "liquidity_usd": float(p["liquidity"] or 0),
                     "fee_tier": int(p["feeTier"] or 0)}
                    for p in rows
                ],
            })
    except Exception as exc:  # noqa: BLE001
        return ProviderResult(None, str(exc))


# ---------------------------------------------------- Etherscan on-chain flow

async def fetch_etherscan_exchange_flow(address: str, tag: str = "latest") -> ProviderResult:
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        return ProviderResult(None, "ETHERSCAN_API_KEY not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=_ssl_setting()) as client:
        try:
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={"module": "account", "action": "balance",
                        "address": address, "tag": tag, "apikey": api_key},
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code >= 400:
                return ProviderResult(None, f"etherscan {resp.status_code}")
            payload = resp.json() or {}
            return ProviderResult({"address": address, "balance_wei": payload.get("result")})
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(None, str(exc))


# ----- Aggregator fan-outs the snapshot pipeline calls per category ----

async def collect_fundamentals(symbols: list[str]) -> dict[str, Any]:
    """CoinGecko + DeFiLlama + Fear & Greed in parallel."""
    out: dict[str, Any] = {}
    async def _task(name: str, coro) -> None:
        try:
            res = await coro
            if res.value is None:
                out[name] = {"error": res.error}
            else:
                out[name] = res.value
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": str(exc)}

    await asyncio.gather(
        _task("coingecko_global", fetch_coingecko_global()),
        _task("coingecko_prices", fetch_coingecko_simple_price(symbols)),
        _task("defillama_global", fetch_defillama_global_tvl()),
        _task("fear_and_greed", fetch_fear_and_greed()),
    )
    return out


async def collect_macro() -> dict[str, Any]:
    out: dict[str, Any] = {}
    res = await fetch_fred_macro()
    out["fred"] = res.value if res.value is not None else {"error": res.error}
    fx = await fetch_fx_reference()
    out["fx"] = fx.value if fx.value is not None else {"error": fx.error}
    return out


async def collect_sentiment(symbol: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    res = await fetch_stocktwits_symbol(symbol)
    out["stocktwits"] = res.value if res.value is not None else {"error": res.error}
    news = await fetch_google_news_rss(f"{symbol} crypto when:1d")
    out["news"] = news.value if news.value is not None else {"error": news.error}
    fn = await fetch_finnhub_news(symbol)
    if fn.value is not None:
        out["news_2"] = fn.value
    return out


__all__ = [
    "ProviderError",
    "ProviderResult",
    "fetch_coingecko_global",
    "fetch_coingecko_simple_price",
    "fetch_defillama_global_tvl",
    "fetch_defillama_protocols",
    "fetch_fear_and_greed",
    "fetch_fx_reference",
    "fetch_fred_macro",
    "fetch_stocktwits_symbol",
    "fetch_finnhub_news",
    "fetch_finnhub_calendar",
    "fetch_google_news_rss",
    "fetch_uniswap_v3_pool",
    "fetch_top_uniswap_pools",
    "fetch_etherscan_exchange_flow",
    "collect_fundamentals",
    "collect_macro",
    "collect_sentiment",
]

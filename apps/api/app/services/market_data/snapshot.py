"""Canonical market snapshot + resilient data pipeline.

One normalized object feeds every gate. Fetches are rate-budgeted, cached by
category, and fail over across compatible providers. Expired cache entries are
retained briefly as explicitly-stale fallback; synthetic data is never mixed
into a live snapshot.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

from app.schemas.candle import Candle
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

CATEGORY_TTLS: dict[str, int] = {
    "ohlcv": 60,
    "orderbook": 5,
    "funding": 300,
    "liquidations": 300,
    "fundamentals": 3600,
    "news": 900,
    "on_chain": 1800,
    "dex_pools": 30,
    "tranches": 120,
    "macro": 3600,
    "sentiment": 600,
}


@dataclass(frozen=True)
class DataProvenance:
    provider: str
    fetched_at: str
    is_stale: bool = False
    cache_age_seconds: float = 0.0
    failover_from: str | None = None


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    as_of: str
    candles: list[Candle] = field(default_factory=list)
    order_book: dict[str, Any] | None = None
    funding_rate: float | None = None
    predicted_funding: float | None = None
    oi_change_pct: float | None = None
    long_short_ratio: float | None = None
    liquidation_clusters: list[dict[str, Any]] = field(default_factory=list)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    on_chain: dict[str, Any] = field(default_factory=dict)
    news: list[dict[str, Any]] = field(default_factory=list)
    dex_pools: list[dict[str, Any]] = field(default_factory=list)
    tranches: list[dict[str, Any]] = field(default_factory=list)
    macro: dict[str, Any] = field(default_factory=dict)
    sentiment: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, DataProvenance] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def stale_categories(self) -> list[str]:
        return [name for name, meta in self.provenance.items() if meta.is_stale]

    @property
    def symbol_meta(self) -> dict[str, Any]:
        """Side-data shape consumed by GateContext."""
        return {
            "is_active": True,
            "funding_rate": self.funding_rate,
            "predicted_funding": self.predicted_funding,
            "oi_change_pct": self.oi_change_pct,
            "long_short_ratio": self.long_short_ratio,
            "liquidation_clusters": self.liquidation_clusters,
            "fundamentals": self.fundamentals,
            "on_chain": self.on_chain,
            "dex_pools": self.dex_pools,
            "tranches": self.tranches,
            "macro": self.macro,
            "sentiment": self.sentiment,
            "data_provenance": {
                key: asdict(value) for key, value in self.provenance.items()
            },
            "stale_categories": self.stale_categories,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of": self.as_of,
            "candles": [c.model_dump(mode="json") for c in self.candles],
            "order_book": self.order_book,
            "funding_rate": self.funding_rate,
            "predicted_funding": self.predicted_funding,
            "oi_change_pct": self.oi_change_pct,
            "long_short_ratio": self.long_short_ratio,
            "liquidation_clusters": self.liquidation_clusters,
            "fundamentals": self.fundamentals,
            "on_chain": self.on_chain,
            "news": self.news,
            "dex_pools": self.dex_pools,
            "tranches": self.tranches,
            "macro": self.macro,
            "sentiment": self.sentiment,
            "provenance": {k: asdict(v) for k, v in self.provenance.items()},
            "errors": self.errors,
            "stale_categories": self.stale_categories,
        }


class RateLimitExceeded(RuntimeError):
    pass


class RateLimitBudget:
    """Concurrency-safe token bucket per provider."""

    def __init__(self, capacity: int = 60, refill_per_second: float = 1.0):
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("rate-limit capacity and refill rate must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_second
        self._tokens = float(capacity)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, wait: bool = True) -> None:
        if tokens <= 0 or tokens > self.capacity:
            raise ValueError("token request must be within bucket capacity")
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity,
                    self._tokens + (now - self._updated_at) * self.refill_per_second,
                )
                self._updated_at = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                delay = (tokens - self._tokens) / self.refill_per_second
            if not wait:
                raise RateLimitExceeded("provider request budget exhausted")
            await asyncio.sleep(delay)


class SnapshotCache:
    """JSON cache using Redis or the in-process Redis-compatible shim."""

    def __init__(self, client: Any, namespace: str = "market-snapshot"):
        self.client = client
        self.namespace = namespace

    def _key(self, category: str, provider: str, symbol: str, timeframe: str) -> str:
        normalized = symbol.replace("/", "-").upper()
        return f"{self.namespace}:{provider}:{category}:{normalized}:{timeframe}"

    async def get(
        self, category: str, provider: str, symbol: str, timeframe: str
    ) -> tuple[Any, DataProvenance] | None:
        key = self._key(category, provider, symbol, timeframe)
        raw = await self.client.get(key)
        if not raw:
            return None
        try:
            envelope = json.loads(raw)
            fetched_at = float(envelope["fetched_at_epoch"])
            age = max(0.0, time.time() - fetched_at)
            stale = time.time() > float(envelope["fresh_until_epoch"])
            return envelope["value"], DataProvenance(
                provider=provider,
                fetched_at=datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
                is_stale=stale,
                cache_age_seconds=round(age, 3),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("discarding malformed snapshot cache entry %s", key)
            return None

    async def set(
        self,
        category: str,
        provider: str,
        symbol: str,
        timeframe: str,
        value: Any,
        ttl: int,
    ) -> DataProvenance:
        now = time.time()
        envelope = {
            "fetched_at_epoch": now,
            "fresh_until_epoch": now + ttl,
            "value": value,
        }
        # Retain stale data for failover, but mark freshness using envelope time.
        await self.client.setex(
            self._key(category, provider, symbol, timeframe),
            max(ttl * 10, ttl + 60),
            json.dumps(envelope, separators=(",", ":")),
        )
        return DataProvenance(
            provider=provider,
            fetched_at=datetime.fromtimestamp(now, timezone.utc).isoformat(),
        )


CategoryFetcher = Callable[[MarketDataProvider, str, str, int], Awaitable[Any]]


async def _fetch_ohlcv(
    provider: MarketDataProvider, symbol: str, timeframe: str, limit: int
) -> list[dict[str, Any]]:
    rows = await provider.get_ohlcv(symbol, timeframe, limit)
    return [c.model_dump(mode="json") for c in rows]


async def _fetch_orderbook(
    provider: MarketDataProvider, symbol: str, timeframe: str, limit: int
) -> dict[str, Any] | None:
    method = getattr(provider, "get_order_book", None)
    if method is None:
        raise NotImplementedError(f"{provider.name} has no orderbook adapter")
    return await method(symbol, min(limit, 100))


async def _fetch_fundamentals(
    _provider: MarketDataProvider, symbol: str, _timeframe: str, _limit: int
) -> dict[str, Any]:
    from app.services.market_data.free_sources import collect_fundamentals
    return await collect_fundamentals([symbol])


async def _fetch_macro(
    _provider: MarketDataProvider, _symbol: str, _timeframe: str, _limit: int
) -> dict[str, Any]:
    from app.services.market_data.free_sources import collect_macro
    return await collect_macro()


async def _fetch_sentiment(
    _provider: MarketDataProvider, symbol: str, _timeframe: str, _limit: int
) -> dict[str, Any]:
    from app.services.market_data.free_sources import collect_sentiment
    return await collect_sentiment(symbol)


async def _fetch_dex_pools(
    _provider: MarketDataProvider, _symbol: str, _timeframe: str, _limit: int
) -> dict[str, Any]:
    from app.services.market_data.dex import aggregate_network_state
    return await aggregate_network_state(network=_timeframe or "ethereum")


async def _fetch_tranches(
    _provider: MarketDataProvider, _symbol: str, _timeframe: str, _limit: int
) -> dict[str, Any]:
    from app.services.market_data.dex import discover_robinhood_tranches_on_base
    return await discover_robinhood_tranches_on_base()


DEFAULT_FETCHERS: dict[str, CategoryFetcher] = {
    "ohlcv": _fetch_ohlcv,
    "orderbook": _fetch_orderbook,
    "fundamentals": _fetch_fundamentals,
    "macro": _fetch_macro,
    "sentiment": _fetch_sentiment,
    "dex_pools": _fetch_dex_pools,
    "tranches": _fetch_tranches,
}


class MarketSnapshotPipeline:
    def __init__(
        self,
        providers: Iterable[MarketDataProvider],
        cache: SnapshotCache,
        *,
        budgets: dict[str, RateLimitBudget] | None = None,
        fetchers: dict[str, CategoryFetcher] | None = None,
        ttls: dict[str, int] | None = None,
    ):
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("at least one market-data provider is required")
        self.cache = cache
        self.budgets = budgets or {}
        self.fetchers = {**DEFAULT_FETCHERS, **(fetchers or {})}
        self.ttls = {**CATEGORY_TTLS, **(ttls or {})}

    async def _category(
        self,
        category: str,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> tuple[Any, DataProvenance, str | None]:
        fetcher = self.fetchers[category]
        primary_name = self.providers[0].name
        # Result shape depends on requested depth. Keep 50-bar and 300-bar
        # callers from sharing one cache entry.
        cache_timeframe = f"{timeframe}:{limit}"
        stale_candidate: tuple[Any, DataProvenance] | None = None

        for provider in self.providers:
            cached = await self.cache.get(category, provider.name, symbol, cache_timeframe)
            if cached and not cached[1].is_stale:
                provenance = cached[1]
                if provider.name != primary_name:
                    provenance = DataProvenance(
                        **{**asdict(provenance), "failover_from": primary_name}
                    )
                return cached[0], provenance, None
            if cached and stale_candidate is None:
                stale_candidate = cached

            try:
                budget = self.budgets.setdefault(
                    provider.name, RateLimitBudget(capacity=60, refill_per_second=1)
                )
                await budget.acquire()
                value = await fetcher(provider, symbol, timeframe, limit)
                if value is None:
                    raise RuntimeError("provider returned no data")
                provenance = await self.cache.set(
                    category, provider.name, symbol, cache_timeframe, value, self.ttls[category]
                )
                if provider.name != primary_name:
                    provenance = DataProvenance(
                        **{**asdict(provenance), "failover_from": primary_name}
                    )
                return value, provenance, None
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "%s fetch failed via %s for %s: %s",
                    category, provider.name, symbol, exc,
                )

        if stale_candidate:
            value, provenance = stale_candidate
            return value, provenance, "all providers failed; using stale cache"
        raise RuntimeError(f"{category} unavailable from all providers")

    async def build(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 300,
        categories: tuple[str, ...] = ("ohlcv", "orderbook"),
    ) -> MarketSnapshot:
        normalized = symbol.replace("-", "/").upper()
        snapshot = MarketSnapshot(
            symbol=normalized,
            timeframe=timeframe,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

        async def collect(category: str) -> None:
            if category not in self.fetchers:
                snapshot.errors[category] = "no adapter configured"
                return
            try:
                value, provenance, warning = await self._category(
                    category, normalized, timeframe, limit
                )
                snapshot.provenance[category] = provenance
                if warning:
                    snapshot.errors[category] = warning
                if category == "ohlcv":
                    snapshot.candles = [Candle.model_validate(row) for row in value]
                elif category == "orderbook":
                    snapshot.order_book = value
                elif category == "funding" and isinstance(value, dict):
                    snapshot.funding_rate = value.get("funding_rate")
                    snapshot.predicted_funding = value.get("predicted_funding")
                    snapshot.oi_change_pct = value.get("oi_change_pct")
                    snapshot.long_short_ratio = value.get("long_short_ratio")
                elif category == "liquidations":
                    snapshot.liquidation_clusters = list(value or [])
                elif category == "fundamentals":
                    snapshot.fundamentals = dict(value or {})
                elif category == "on_chain":
                    snapshot.on_chain = dict(value or {})
                elif category == "news":
                    snapshot.news = list(value or [])
                elif category == "dex_pools":
                    snapshot.dex_pools = list(value or [])
                elif category == "tranches":
                    snapshot.tranches = list(value or [])
                elif category == "macro":
                    snapshot.macro = dict(value or {})
                elif category == "sentiment":
                    snapshot.sentiment = dict(value or {})
            except Exception as exc:  # noqa: BLE001
                snapshot.errors[category] = str(exc)

        await asyncio.gather(*(collect(category) for category in categories))
        return snapshot


__all__ = [
    "CATEGORY_TTLS",
    "DataProvenance",
    "MarketSnapshot",
    "MarketSnapshotPipeline",
    "RateLimitBudget",
    "RateLimitExceeded",
    "SnapshotCache",
]

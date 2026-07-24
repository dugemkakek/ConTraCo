"""In-process TTL cache for CoinGecko GET requests.

CoinGecko's free tier allows roughly 10-30 calls/min, and this app hits it
from several scattered call sites (arbitrage scanner, on-chain metrics,
derivatives funding/OI, intel trenches, global market cap, simple price).
Under load the same URL gets fetched multiple times within seconds, risking
HTTP 429 across *all* consumers.

This module wraps a plain ``client.get(...)`` call so each call site keeps
its own status/error convention — a one-token diff at the call site:

    resp = await cached_get(client, url, params=params)

Design choices:
  * Cache the ``httpx.Response`` object itself. Only ``status == 200``
    responses are stored — errors/exceptions pass through untouched so a
    transient 429 never poisons the cache and every caller's own fallback
    behavior (raise, log+skip, Binance fallback, ProviderResult error)
    still fires.
  * Per-key ``asyncio.Lock`` for single-flight: concurrent callers for one
    key share a single upstream request. The expiry check is re-run after
    acquiring the lock so waiters hit the freshly-filled cache.
  * ``time.monotonic()`` for expiry (immune to wall-clock changes).
  * Bounded size with oldest-entry eviction to avoid unbounded growth from
    distinct param combinations (e.g. per-coin ticker fetches).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

DEFAULT_TTL = 60.0  # seconds
MAX_ENTRIES = 512

# key -> (expires_at_monotonic, response)
_cache: dict[str, tuple[float, httpx.Response]] = {}
# key -> per-key lock (single-flight)
_locks: dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()  # guards _locks creation only


def _key(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    norm = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{url}?{norm}"


async def _lock_for(key: str) -> asyncio.Lock:
    async with _global_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _locks[key] = lock
        return lock


def _evict_if_needed() -> None:
    """Drop oldest entries once over capacity. Plain (non-async) — call it
    while holding a per-key lock or _global_lock context is not required
    because only one coroutine is writing to _cache at a time within a
    single event loop tick."""
    if len(_cache) <= MAX_ENTRIES:
        return
    for k, _v in sorted(_cache.items(), key=lambda kv: kv[1][0]):
        _cache.pop(k, None)
        if len(_cache) <= MAX_ENTRIES * 0.9:
            break


async def cached_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    ttl: float = DEFAULT_TTL,
) -> httpx.Response:
    """GET ``url`` through a TTL cache, returning the raw ``httpx.Response``.

    Only 200 responses are cached; non-200 responses and exceptions pass
    straight through so each call site keeps its own error convention.
    """
    key = _key(url, params)
    now = time.monotonic()
    entry = _cache.get(key)
    if entry is not None and entry[0] > now:
        return entry[1]

    lock = await _lock_for(key)
    async with lock:
        # Re-check after acquiring the lock: another waiter may have filled it.
        now = time.monotonic()
        entry = _cache.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]

        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            _cache[key] = (time.monotonic() + ttl, resp)
            _evict_if_needed()
        return resp


def clear() -> None:
    """Empty the cache (for tests and manual resets)."""
    _cache.clear()
    _locks.clear()

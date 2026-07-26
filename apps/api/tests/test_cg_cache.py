"""Tests for the shared in-process TTL cache for CoinGecko GETs.

CoinGecko's free tier allows ~10-30 calls/min, and the app hits it from
several scattered endpoints. The cache must:
  * dedupe identical GETs (url + params) within the TTL,
  * treat param order as irrelevant,
  * re-fetch after the TTL expires,
  * NEVER cache errors (429/5xx/network) — each call site has its own
    fallback behavior and a cached 429 would poison every consumer,
  * single-flight concurrent callers for one key.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.market_data import cg_cache

URL = "https://api.coingecko.com/api/v3/global"


@pytest.fixture(autouse=True)
def _empty_cache():
    cg_cache.clear()
    yield
    cg_cache.clear()


def _counting_client(payload: dict, status: int = 200):
    count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), count


async def test_repeat_get_within_ttl_hits_upstream_once():
    client, count = _counting_client({"ok": True})
    async with client:
        r1 = await cg_cache.cached_get(client, URL)
        r2 = await cg_cache.cached_get(client, URL)
    assert count["n"] == 1
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json() == {"ok": True}


async def test_param_order_does_not_split_cache():
    client, count = _counting_client({"ok": True})
    async with client:
        await cg_cache.cached_get(client, URL, params={"a": "1", "b": "2"})
        await cg_cache.cached_get(client, URL, params={"b": "2", "a": "1"})
    assert count["n"] == 1


async def test_different_params_are_distinct_keys():
    client, count = _counting_client({"ok": True})
    async with client:
        await cg_cache.cached_get(client, URL, params={"ids": "bitcoin"})
        await cg_cache.cached_get(client, URL, params={"ids": "ethereum"})
    assert count["n"] == 2


async def test_expired_entry_is_refetched(monkeypatch):
    now = {"t": 1_000.0}
    monkeypatch.setattr(cg_cache.time, "monotonic", lambda: now["t"])
    client, count = _counting_client({"ok": True})
    async with client:
        await cg_cache.cached_get(client, URL, ttl=60)
        now["t"] += 61  # past the 60s TTL
        await cg_cache.cached_get(client, URL, ttl=60)
    assert count["n"] == 2


async def test_http_errors_are_not_cached():
    responses = [
        httpx.Response(429, json={"error": "slow down"}),
        httpx.Response(200, json={"ok": True}),
    ]
    count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses[min(count["n"], len(responses) - 1)]
        count["n"] += 1
        return resp

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r1 = await cg_cache.cached_get(client, URL)
        r2 = await cg_cache.cached_get(client, URL)
    assert count["n"] == 2
    assert r1.status_code == 429
    assert r2.status_code == 200


async def test_network_errors_are_not_cached():
    count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        if count["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            await cg_cache.cached_get(client, URL)
        r2 = await cg_cache.cached_get(client, URL)
    assert count["n"] == 2
    assert r2.status_code == 200


async def test_concurrent_callers_share_one_upstream_request():
    count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        await asyncio.sleep(0.02)  # force interleaving with the other callers
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await asyncio.gather(
            *(cg_cache.cached_get(client, URL) for _ in range(6))
        )
    assert count["n"] == 1
    assert all(r.json() == {"ok": True} for r in results)

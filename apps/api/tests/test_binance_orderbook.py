"""Tests for the Binance orderbook adapter.

Regression coverage for two bugs:
1. The adapter method was named ``get_orderbook`` while the snapshot pipeline
   and the /orderbook route discover it via ``get_order_book`` — so Binance
   silently served mock data.
2. The adapter called api.binance.com directly (geo-blocked from this
   deployment) instead of routing through ``_get_with_fallback``, which tries
   data-api.binance.vision the way ``get_ohlcv`` already does.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.market_data.binance_rest import (
    BINANCE_REST_BASE,
    BINANCE_REST_FALLBACKS,
    BinanceRestProvider,
)

DEPTH_JSON = {
    "lastUpdateId": 123,
    "bids": [["65000.10", "0.5"], ["65000.00", "1.25"]],
    "asks": [["65000.20", "0.75"], ["65000.30", "2.0"]],
}

ALLOWED_LIMITS = {5, 10, 20, 50, 100, 500, 1000, 5000}


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeClient:
    """httpx.AsyncClient stand-in: answers per-URL and records requests."""

    def __init__(self, responder):
        self.responder = responder
        self.requests: list[tuple[str, dict]] = []

    async def get(self, url, params=None):
        self.requests.append((url, params or {}))
        return self.responder(url, params or {})


def _patch_client(monkeypatch, provider: BinanceRestProvider, client: FakeClient):
    async def _get_client():
        return client

    monkeypatch.setattr(provider, "_get_client", _get_client)


def test_binance_provider_exposes_get_order_book_interface():
    # Discovered via getattr/hasattr("get_order_book") in snapshot.py / orderbook.py.
    assert hasattr(BinanceRestProvider(), "get_order_book")


@pytest.mark.asyncio
async def test_get_order_book_falls_back_to_binance_vision(monkeypatch):
    def responder(url, _params):
        if BINANCE_REST_BASE in url:
            raise httpx.ConnectError("geo-blocked")
        assert any(fb in url for fb in BINANCE_REST_FALLBACKS), url
        return FakeResponse(200, DEPTH_JSON)

    provider = BinanceRestProvider()
    fake = FakeClient(responder)
    _patch_client(monkeypatch, provider, fake)

    book = await provider.get_order_book("BTC/USDT", 20)

    assert book is not None
    assert book["bids"] == [[65000.10, 0.5], [65000.00, 1.25]]
    assert book["asks"] == [[65000.20, 0.75], [65000.30, 2.0]]
    assert book["lastUpdateId"] == 123
    # Primary base attempted first, then the fallback.
    assert len(fake.requests) == 2
    assert BINANCE_REST_BASE in fake.requests[0][0]
    assert fake.requests[1][1]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_get_order_book_snaps_depth_to_binance_limits(monkeypatch):
    provider = BinanceRestProvider()
    fake = FakeClient(lambda _url, _params: FakeResponse(200, DEPTH_JSON))
    _patch_client(monkeypatch, provider, fake)

    await provider.get_order_book("BTC/USDT", 25)

    sent_limit = fake.requests[-1][1]["limit"]
    assert sent_limit in ALLOWED_LIMITS
    assert sent_limit >= 25, "must not under-deliver requested depth"


@pytest.mark.asyncio
async def test_get_order_book_returns_none_when_all_bases_fail(monkeypatch):
    def responder(_url, _params):
        raise httpx.ConnectError("blocked")

    provider = BinanceRestProvider()
    _patch_client(monkeypatch, provider, FakeClient(responder))

    assert await provider.get_order_book("BTC/USDT", 20) is None

"""Tests for funding-history source selection (Hyperliquid time series primary).

Binance fapi (real history) is geo-blocked in some regions and CoinGecko
derivatives only gives a current snapshot. Hyperliquid's public info API
serves real hourly funding history with no key and no geo-block, so it is
the preferred history source; CoinGecko snapshot and Binance fapi remain
as fallbacks.
"""
from __future__ import annotations

import pytest

from app.services.market_data import derivatives as m
from app.services.market_data.derivatives import _map_hl_funding, get_funding_history

HL_PAYLOAD = [
    {"coin": "BTC", "fundingRate": "0.0000125", "premium": "0.0001249961", "time": 1752001200114},
    {"coin": "BTC", "fundingRate": "0.0001", "premium": "0.0002", "time": 1752004800017},
    {"coin": "BTC", "fundingRate": "-0.00003", "premium": "-0.00004", "time": 1752008400059},
]


def test_hl_payload_maps_to_rows():
    rows = _map_hl_funding(HL_PAYLOAD, limit=100)
    assert rows == [
        {"time": 1752001200114, "funding_rate": 0.0000125, "premium": 0.0001249961, "exchange": "hyperliquid"},
        {"time": 1752004800017, "funding_rate": 0.0001, "premium": 0.0002, "exchange": "hyperliquid"},
        {"time": 1752008400059, "funding_rate": -0.00003, "premium": -0.00004, "exchange": "hyperliquid"},
    ]


def test_hl_rows_respect_limit_keeping_most_recent():
    rows = _map_hl_funding(HL_PAYLOAD, limit=2)
    assert len(rows) == 2
    assert rows[0]["time"] == 1752004800017
    assert rows[1]["time"] == 1752008400059


def test_hl_mapping_skips_garbage_entries():
    payload = [
        {"coin": "BTC", "fundingRate": "not-a-number", "time": 1},
        {"coin": "BTC", "premium": "0.1", "time": 2},  # no fundingRate
        {"coin": "BTC", "fundingRate": "0.0001"},  # no time
        {"coin": "BTC", "fundingRate": "0.0002", "premium": "0.0003", "time": 4},
    ]
    rows = _map_hl_funding(payload, limit=100)
    assert rows == [{"time": 4, "funding_rate": 0.0002, "premium": 0.0003, "exchange": "hyperliquid"}]


def test_hl_mapping_empty_input():
    assert _map_hl_funding([], limit=10) == []


async def test_hyperliquid_preferred_when_available(monkeypatch):
    hl_rows = [{"time": 1, "funding_rate": 0.0001, "premium": 0.0, "exchange": "hyperliquid"}]

    async def fake_hl(symbol, limit):
        return hl_rows

    async def should_not_be_called(symbol, limit):  # pragma: no cover
        raise AssertionError("fallback fetcher should not run when Hyperliquid has rows")

    monkeypatch.setattr(m, "_fetch_hyperliquid_history", fake_hl)
    monkeypatch.setattr(m, "_fetch_coingecko_funding_snapshot", should_not_be_called)
    monkeypatch.setattr(m, "_fetch_binance_funding", should_not_be_called)

    out = await get_funding_history("BTCUSDT", limit=10)
    assert out["source"] == "hyperliquid"
    assert out["rows"] == hl_rows
    assert out["symbol"] == "BTCUSDT"


async def test_coingecko_snapshot_used_when_hl_unavailable(monkeypatch):
    cg_rows = [{"time": 5, "funding_rate": 0.005, "exchange": "Binance (Futures)"}]

    async def none_hl(symbol, limit):
        return None

    async def fake_cg(symbol, limit):
        return cg_rows

    async def should_not_be_called(symbol, limit):  # pragma: no cover
        raise AssertionError("binance fallback should not run when CoinGecko has rows")

    monkeypatch.setattr(m, "_fetch_hyperliquid_history", none_hl)
    monkeypatch.setattr(m, "_fetch_coingecko_funding_snapshot", fake_cg)
    monkeypatch.setattr(m, "_fetch_binance_funding", should_not_be_called)

    out = await get_funding_history("BTCUSDT", limit=10)
    assert out["source"] == "coingecko"
    assert out["rows"] == cg_rows


async def test_binance_fapi_used_as_last_fallback(monkeypatch):
    fapi_rows = [{"time": 9, "funding_rate": 0.0001}]

    async def none_fetcher(symbol, limit):
        return None

    async def fake_fapi(symbol, limit):
        return fapi_rows

    monkeypatch.setattr(m, "_fetch_hyperliquid_history", none_fetcher)
    monkeypatch.setattr(m, "_fetch_coingecko_funding_snapshot", none_fetcher)
    monkeypatch.setattr(m, "_fetch_binance_funding", fake_fapi)

    out = await get_funding_history("BTCUSDT", limit=10)
    assert out["source"] == "binance-fapi"
    assert out["rows"] == fapi_rows


async def test_all_sources_unavailable(monkeypatch):
    async def none_fetcher(symbol, limit):
        return None

    monkeypatch.setattr(m, "_fetch_hyperliquid_history", none_fetcher)
    monkeypatch.setattr(m, "_fetch_coingecko_funding_snapshot", none_fetcher)
    monkeypatch.setattr(m, "_fetch_binance_funding", none_fetcher)

    out = await get_funding_history("BTCUSDT", limit=10)
    assert out["source"] == "unavailable"
    assert out["rows"] == []


async def test_empty_rows_fall_through_to_next_source(monkeypatch):
    """A source returning [] (reachable but no data) must not short-circuit."""
    cg_rows = [{"time": 5, "funding_rate": 0.005, "exchange": "okx"}]

    async def empty_hl(symbol, limit):
        return []

    async def fake_cg(symbol, limit):
        return cg_rows

    async def none_fapi(symbol, limit):
        return None

    monkeypatch.setattr(m, "_fetch_hyperliquid_history", empty_hl)
    monkeypatch.setattr(m, "_fetch_coingecko_funding_snapshot", fake_cg)
    monkeypatch.setattr(m, "_fetch_binance_funding", none_fapi)

    out = await get_funding_history("BTCUSDT", limit=10)
    assert out["source"] == "coingecko"

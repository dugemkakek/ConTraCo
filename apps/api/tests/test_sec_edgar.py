"""Tests for the SEC EDGAR fetcher (apps/api/app/services/fundamentals/sec_edgar.py).

Fixtures mirror verified live-SEC quirks:
  * AAPL retired the ``Revenues`` XBRL tag after FY2018 — recent revenue
    lives under ``RevenueFromContractWithCustomerExcludingAssessedTax``.
  * The same period-end can carry both a quarterly (10-Q) and an annual
    (10-K FY) value; the fundamentals snapshot should prefer the annual one.
  * EPS lives in a ``USD/shares`` unit bucket, not ``USD`` or ``shares``.
  * browse-edgar's ``company=`` param matches company NAMES, so searching
    it with a ticker returns nothing — the ``CIK=`` param (which also
    accepts tickers) must be used instead.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.fundamentals import sec_edgar

TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}

# us-gaap:Revenues for AAPL — stale, ends FY2018, with a quarterly value
# and an annual value sharing the 2018-09-29 period-end.
REVENUES_LEGACY = {
    "entityName": "Apple Inc.",
    "units": {
        "USD": [
            {"val": 61000000000, "end": "2017-09-30", "fy": "2017", "fp": "FY",
             "form": "10-K", "filed": "2017-11-03", "frame": "CY2017"},
            {"val": 62900000000, "end": "2018-09-29", "fy": "2018", "fp": "Q3",
             "form": "10-Q", "filed": "2018-08-01", "frame": "CY2018Q3"},
            {"val": 265595000000, "end": "2018-09-29", "fy": "2018", "fp": "FY",
             "form": "10-K", "filed": "2018-11-05", "frame": "CY2018"},
        ]
    },
}

# us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — the tag
# AAPL actually files under now.
REVENUE_MODERN = {
    "entityName": "Apple Inc.",
    "units": {
        "USD": [
            {"val": 394328000000, "end": "2024-09-28", "fy": "2024", "fp": "FY",
             "form": "10-K", "filed": "2024-11-01", "frame": "CY2024"},
            {"val": 416246000000, "end": "2025-09-27", "fy": "2025", "fp": "FY",
             "form": "10-K", "filed": "2025-10-31", "frame": "CY2025"},
        ]
    },
}

NET_INCOME = {
    "entityName": "Apple Inc.",
    "units": {
        "USD": [
            {"val": 93736000000, "end": "2025-09-27", "fy": "2025", "fp": "FY",
             "form": "10-K", "filed": "2025-10-31", "frame": "CY2025"},
            {"val": 24780000000, "end": "2026-03-28", "fy": "2026", "fp": "Q1",
             "form": "10-Q", "filed": "2026-05-01", "frame": "CY2026Q1"},
        ]
    },
}

EPS = {
    "entityName": "Apple Inc.",
    "units": {
        "USD/shares": [
            {"val": 6.99, "end": "2025-09-27", "fy": "2025", "fp": "FY",
             "form": "10-K", "filed": "2025-10-31", "frame": None},
            {"val": 1.65, "end": "2026-03-28", "fy": "2026", "fp": "Q1",
             "form": "10-Q", "filed": "2026-05-01", "frame": None},
        ]
    },
}

ASSETS = {
    "entityName": "Apple Inc.",
    "units": {
        "USD": [
            {"val": 364980000000, "end": "2025-09-27", "fy": "2025", "fp": "FY",
             "form": "10-K", "filed": "2025-10-31", "frame": "CY2025I"},
        ]
    },
}

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>EDGAR Filing Documents for 0000320193</title>
  <entry>
    <title>10-K  - Annual report [Section 13 and 15(d)]</title>
    <updated>2025-10-31T16:01:00-05:00</updated>
    <link href="https://www.sec.gov/Archives/edgar/data/320193/a-index.htm" />
  </entry>
  <entry>
    <title>10-K  - Annual report [Section 13 and 15(d)]</title>
    <updated>2024-11-01T16:01:00-05:00</updated>
    <link href="https://www.sec.gov/Archives/edgar/data/320193/b-index.htm" />
  </entry>
</feed>
"""


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else ""

    def json(self):
        return self._payload


class _FakeClient:
    """Mimics httpx.AsyncClient well enough for sec_edgar.

    browse-edgar behaves like the real service: the ``company=`` param
    only matches company NAMES (a ticker yields zero entries), while
    ``CIK=`` accepts a ticker or CIK.
    """

    def __init__(self, calls: list):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        params = dict(params or {})
        self._calls.append((url, params))
        if "company_tickers.json" in url:
            return _FakeResponse(TICKERS_JSON)
        if "browse-edgar" in url:
            if "company" in params and "CIK" not in params:
                return _FakeResponse(text="<feed xmlns='http://www.w3.org/2005/Atom'></feed>")
            return _FakeResponse(text=ATOM_FEED)
        if "RevenueFromContractWithCustomerExcludingAssessedTax" in url:
            return _FakeResponse(REVENUE_MODERN)
        if "/Revenues.json" in url:
            return _FakeResponse(REVENUES_LEGACY)
        if "/NetIncomeLoss.json" in url:
            return _FakeResponse(NET_INCOME)
        if "/EarningsPerShareDiluted.json" in url:
            return _FakeResponse(EPS)
        if "/Assets.json" in url:
            return _FakeResponse(ASSETS)
        return _FakeResponse(payload={}, status_code=404)


@pytest.fixture
def sec_calls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "app.services.fundamentals.sec_edgar.httpx.AsyncClient",
        lambda **_kwargs: _FakeClient(calls),
    )
    return calls


def test_facts_revenue_falls_back_to_modern_concept(sec_calls):
    """AAPL's Revenues tag is stale (FY2018); recent revenue must come
    from RevenueFromContractWithCustomerExcludingAssessedTax."""
    facts = asyncio.run(sec_edgar.get_company_facts("AAPL"))
    assert facts is not None
    assert facts["revenue"]["value"] == 416246000000
    assert facts["revenue"]["period"] == "2025-09-27"


def test_facts_prefers_annual_over_quarterly(sec_calls):
    """Net income has both a 10-K FY2025 and a 10-Q Q1-2026 value —
    the fundamentals snapshot should carry the annual figure."""
    facts = asyncio.run(sec_edgar.get_company_facts("AAPL"))
    assert facts["net_income"]["value"] == 93736000000
    assert facts["net_income"]["form"] == "10-K"


def test_facts_eps_reads_usd_shares_bucket(sec_calls):
    """EPS is filed under units USD/shares, not USD or shares."""
    facts = asyncio.run(sec_edgar.get_company_facts("AAPL"))
    assert facts["eps_diluted"] is not None
    assert facts["eps_diluted"]["value"] == 6.99


def test_search_filings_uses_cik_not_company_param(sec_calls):
    """browse-edgar's company= param matches names, not tickers."""
    results = asyncio.run(sec_edgar.search_filings("AAPL", "10-K", limit=5))
    browse_calls = [(u, p) for u, p in sec_calls if "browse-edgar" in u]
    assert browse_calls, "browse-edgar was never called"
    for _url, params in browse_calls:
        assert "CIK" in params
        assert "company" not in params
    assert len(results) == 2
    assert results[0]["url"].endswith("a-index.htm")
    assert results[0]["filing_date"].startswith("2025-10-31")


def test_company_context_happy_path_merges_filings(sec_calls):
    ctx = asyncio.run(sec_edgar.get_company_context("AAPL"))
    assert ctx["available"] is True
    assert ctx["company_name"] == "Apple Inc."
    assert ctx["cik"] == "0000320193"
    assert set(ctx["financials"]) == {"revenue", "net_income", "eps_diluted", "total_assets"}
    assert ctx["financials"]["total_assets"]["value"] == 364980000000
    # 3× 10-K + 3× 10-Q lookups, capped at limit=3 each by search_filings
    assert len(ctx["recent_filings"]) >= 2


def test_company_context_unavailable_for_non_sec_ticker(sec_calls):
    ctx = asyncio.run(sec_edgar.get_company_context("BTC"))
    assert ctx["available"] is False
    assert "reason" in ctx

"""SEC EDGAR fetcher — company filings and financials via free public API.

No API key required. Uses:
  * https://data.sec.gov/api/ — company facts, filings index
  * https://www.sec.gov/cgi-bin/browse-edgar — filing search
  * https://efts.sec.gov/LATEST/search-index?q= — full-text search

Rate limit: SEC asks for max 10 req/sec with a User-Agent header.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "10.0"))
USER_AGENT = "confluence-trading-consultant/1.0 admin@confluence.local"
BASE = "https://data.sec.gov"
EFTS = "https://efts.sec.gov/LATEST/search-index"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


async def get_company_facts(ticker: str) -> dict[str, Any] | None:
    """Fetch key financial facts for a ticker from SEC EDGAR.

    Returns revenue, net income, EPS, assets, liabilities for the
    most recent periods. Returns None if the ticker is not found
    (e.g. crypto-only symbols).
    """
    async with _client() as client:
        try:
            # First resolve ticker → CIK
            resp = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
            )
            if resp.status_code != 200:
                return None
            tickers_map = resp.json()
            cik = None
            for entry in tickers_map.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    cik = str(entry["cik_str"]).zfill(10)
                    break
            if not cik:
                return None

            # Fetch company facts
            resp = await client.get(f"{BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/Revenues.json")
            revenues = resp.json() if resp.status_code == 200 else None

            resp = await client.get(f"{BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/NetIncomeLoss.json")
            net_income = resp.json() if resp.status_code == 200 else None

            resp = await client.get(f"{BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/EarningsPerShareDiluted.json")
            eps = resp.json() if resp.status_code == 200 else None

            resp = await client.get(f"{BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/Assets.json")
            assets = resp.json() if resp.status_code == 200 else None

            def _latest(concept_data: dict | None) -> dict | None:
                if not concept_data:
                    return None
                units = concept_data.get("units", {})
                usd = units.get("USD") or units.get("shares") or []
                if not usd:
                    return None
                latest = usd[-1]
                return {
                    "value": latest.get("val"),
                    "period": latest.get("end"),
                    "form": latest.get("form"),
                    "frame": latest.get("frame"),
                }

            return {
                "ticker": ticker.upper(),
                "cik": cik,
                "company_name": (revenues or {}).get("entityName", ticker),
                "revenue": _latest(revenues),
                "net_income": _latest(net_income),
                "eps_diluted": _latest(eps),
                "total_assets": _latest(assets),
                "source": "sec_edgar",
            }
        except Exception as exc:
            logger.warning("SEC EDGAR fetch failed for %s: %s", ticker, exc)
            return None


async def search_filings(ticker: str, form_type: str = "10-K", limit: int = 5) -> list[dict[str, Any]]:
    """Search recent SEC filings for a ticker.

    Returns list of {form, filing_date, accession_number, primary_document}.
    """
    async with _client() as client:
        try:
            resp = await client.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcompany",
                    "company": ticker,
                    "type": form_type,
                    "dateb": "",
                    "owner": "include",
                    "count": str(limit),
                    "search_text": "",
                    "output": "atom",
                },
            )
            if resp.status_code != 200:
                return []

            # Parse Atom XML response
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall(".//atom:entry", ns)

            results = []
            for entry in entries[:limit]:
                title = entry.find("atom:title", ns)
                updated = entry.find("atom:updated", ns)
                link = entry.find("atom:link", ns)
                results.append({
                    "form": form_type,
                    "title": title.text if title is not None else "",
                    "filing_date": updated.text if updated is not None else "",
                    "url": link.get("href") if link is not None else "",
                })
            return results
        except Exception as exc:
            logger.warning("SEC filing search failed for %s: %s", ticker, exc)
            return []


async def get_company_context(ticker: str) -> dict[str, Any]:
    """Build a structured fundamental context blob from SEC data.

    Combines company facts + recent filings into a single dict
    suitable for LLM council injection or gate evaluation.
    """
    facts = await get_company_facts(ticker)
    filings = await search_filings(ticker, "10-K", limit=3)
    filings_q = await search_filings(ticker, "10-Q", limit=3)

    if not facts:
        return {
            "ticker": ticker,
            "available": False,
            "reason": "not a SEC-registered entity (crypto or foreign)",
            "source": "sec_edgar",
        }

    return {
        "ticker": ticker,
        "available": True,
        "company_name": facts.get("company_name"),
        "cik": facts.get("cik"),
        "financials": {
            "revenue": facts.get("revenue"),
            "net_income": facts.get("net_income"),
            "eps_diluted": facts.get("eps_diluted"),
            "total_assets": facts.get("total_assets"),
        },
        "recent_filings": filings + filings_q,
        "source": "sec_edgar",
    }

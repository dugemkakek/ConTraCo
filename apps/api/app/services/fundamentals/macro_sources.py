"""Free, no-key macro & on-chain sources for the fundamentals endpoints.

Both feeds below are reachable without an API key or geo-block:

* Economic calendar — faireconomy's ForexFactory JSON mirror
  (``nfs.faireconomy.media``). Returns the current week's events with
  impact, forecast, previous and (once released) actual.
* On-chain metrics — blockchain.info charts API (Bitcoin only, daily
  granularity, free). Hash rate, tx count, active addresses, etc.

These back ``/fundamentals/calendar`` and ``/fundamentals/onchain`` when the
DB tables are empty, so the endpoints serve real data instead of a bare
``[]``. On any upstream failure the fetchers return ``[]`` and the route
degrades gracefully.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FF_CALENDAR = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_SOURCE_URL = "https://www.forexfactory.com/calendar"
BLOCKCHAIN_CHARTS = "https://api.blockchain.info/charts"
TIMEOUT = 12.0

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# blockchain.info charts to surface, in display order. Keys are the chart
# slugs; values are the human metric name we store.
_ONCHAIN_CHARTS: list[tuple[str, str]] = [
    ("n-transactions", "Confirmed Transactions / Day"),
    ("hash-rate", "Hash Rate (TH/s)"),
    ("n-unique-addresses", "Active Addresses / Day"),
    ("miners-revenue", "Miners Revenue (USD)"),
    ("mempool-size", "Mempool Size (bytes)"),
]


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT, verify=False, headers={"User-Agent": _BROWSER_UA}
    )


def _to_float(val: Any) -> float | None:
    """Parse an economic-figure string ('3.4%', '1.2M', '-0.3', '') to float.

    Returns None for blanks / non-numeric values so the caller can leave the
    field null rather than fabricate a zero.
    """
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("%", "")
    if not s or s in {"-", "N/A"}:
        return None
    mult = 1.0
    if s and s[-1] in "KkMmBbTt":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}[s[-1].lower()]
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


async def get_economic_calendar(days: int) -> list[dict[str, Any]]:
    """Upcoming economic events for the next ``days`` days.

    Maps the faireconomy JSON onto the EconomicEventOut shape. The feed's
    ``country`` field is a currency code (USD/EUR/JPY/...), so it doubles as
    both country and currency.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    try:
        async with _client() as c:
            r = await c.get(FF_CALENDAR)
            if r.status_code != 200 or not r.text.strip().startswith("["):
                logger.debug("ff calendar -> %s", r.status_code)
                return []
            data = r.json()
    except Exception:  # noqa: BLE001
        logger.exception("economic calendar fetch failed")
        return []

    out: list[dict[str, Any]] = []
    for i, ev in enumerate(data):
        raw_date = ev.get("date")
        if not raw_date:
            continue
        try:
            when = datetime.fromisoformat(raw_date).astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if when < now or when > horizon:
            continue
        code = (ev.get("country") or "").upper()
        out.append({
            "id": i + 1,
            "event_name": ev.get("title") or "",
            "country": code,
            "currency": code,
            "impact": (ev.get("impact") or "").capitalize() or "Low",
            "actual": _to_float(ev.get("actual")),
            "forecast": _to_float(ev.get("forecast")),
            "previous": _to_float(ev.get("previous")),
            "event_time": when.isoformat(),
            "source_url": FF_SOURCE_URL,
        })
    out.sort(key=lambda x: x["event_time"])
    return out


async def _fetch_chart(c: httpx.AsyncClient, slug: str, name: str,
                       cutoff: datetime) -> list[dict[str, Any]]:
    """One blockchain.info chart -> rows within ``cutoff`` (latest kept always)."""
    try:
        r = await c.get(f"{BLOCKCHAIN_CHARTS}/{slug}",
                        params={"timespan": "30days", "format": "json", "cors": "true"})
        if r.status_code != 200:
            return []
        values = (r.json() or {}).get("values") or []
    except Exception:  # noqa: BLE001
        logger.debug("blockchain.info chart %s failed", slug)
        return []

    rows: list[dict[str, Any]] = []
    for pt in values:
        x, y = pt.get("x"), pt.get("y")
        if x is None or y is None:
            continue
        ts = datetime.fromtimestamp(int(x), tz=timezone.utc)
        rows.append({"metric_name": name, "value": float(y), "_ts": ts})
    # Keep points inside the window, but never drop the single latest point —
    # daily charts may lag the requested window by up to a day.
    within = [row for row in rows if row["_ts"] >= cutoff]
    if not within and rows:
        within = [max(rows, key=lambda r: r["_ts"])]
    return within


async def get_onchain_metrics(hours: int) -> list[dict[str, Any]]:
    """Recent Bitcoin on-chain metrics from blockchain.info (free, no key)."""
    import asyncio

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        async with _client() as c:
            batches = await asyncio.gather(
                *(_fetch_chart(c, slug, name, cutoff) for slug, name in _ONCHAIN_CHARTS)
            )
    except Exception:  # noqa: BLE001
        logger.exception("on-chain metrics fetch failed")
        return []

    out: list[dict[str, Any]] = []
    idx = 0
    for batch in batches:
        for row in batch:
            idx += 1
            out.append({
                "id": idx,
                "symbol": "BTC",
                "metric_name": row["metric_name"],
                "value": row["value"],
                "timestamp": row["_ts"].isoformat(),
            })
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out

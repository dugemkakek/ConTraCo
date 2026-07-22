"""Symbols HTTP surface.

GET /symbols          — registered symbols (auth). Falls back to live Binance.
GET /symbols/venues   — venue catalog (live data providers only — no mock)
GET /symbols/search   — symbol search across Binance + TradingView catalog
GET /symbols/tv-catalog — Raw TradingView public symbol_search results
GET /symbols/spot-pairs  — Live Binance spot pair snapshot
"""


import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import SymbolMeta, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])

# Live-data venues only — the legacy `mock` provider stays out of the UI.
_LIVE_VENUES = {"binance", "bybit", "okx", "kraken", "gateio"}

TV_SYMBOL_SEARCH = "https://symbol-search.tradingview.com/symbol_search/"
BINANCE_REST = "https://api.binance.com"
BINANCE_VISION = "https://data-api.binance.vision"
VERIFY_SSL = os.getenv("FREE_PROVIDER_VERIFY_SSL", "1") == "1"
TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "8.0"))


class SymbolOut(BaseModel):
    symbol: str
    exchange: str
    base: str
    quote: str
    is_active: bool
    price: float | None = None
    change_24h_pct: float | None = None
    volume_24h_quote: float | None = None
    display: str | None = None
    description: str | None = None
    type: str | None = None


def _live_venues() -> list[dict[str, Any]]:
    from app.services.market_data.registry import list_venues
    return [v for v in list_venues() if v["id"] in _LIVE_VENUES]


async def _binance_pairs() -> list[dict[str, Any]]:
    """Fetch live Binance spot pairs from the primary endpoint, with vision fallback."""
    async with httpx.AsyncClient(timeout=TIMEOUT, verify=VERIFY_SSL) as client:
        for base in (BINANCE_VISION, BINANCE_REST):
            try:
                resp = await client.get(f"{base}/api/v3/ticker/24hr")
                if resp.status_code != 200 or not resp.text.strip().startswith("["):
                    continue
                out: list[dict[str, Any]] = []
                for row in resp.json():
                    sym = row.get("symbol", "")
                    if not sym.endswith("USDT"):
                        continue
                    out.append({
                        "symbol": sym,
                        "exchange": "binance",
                        "base": sym[:-4],
                        "quote": "USDT",
                        "display": f"{sym[:-4]}/USDT",
                        "price": float(row.get("lastPrice", 0) or 0),
                        "change_24h_pct": float(row.get("priceChangePercent", 0) or 0),
                        "volume_24h_quote": float(row.get("quoteVolume", 0) or 0),
                        "is_active": True,
                    })
                out.sort(key=lambda x: -x.get("volume_24h_quote", 0))
                return out
            except Exception as exc:  # noqa: BLE001
                logger.debug("binance pairs fetch failed via %s: %s", base, exc)
    return []


async def _tradingview_results(query: str, limit: int) -> list[dict[str, Any]]:
    """Hit the public TradingView symbol_search endpoint."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=VERIFY_SSL) as client:
            resp = await client.get(
                TV_SYMBOL_SEARCH,
                params={"text": query or "BTC", "hl": "en",
                        "exchange": "", "lang": "en"},
            )
            if resp.status_code != 200:
                return []
            out: list[dict[str, Any]] = []
            for row in (resp.json() or []):
                raw_sym = row.get("symbol") or ""
                ex = (row.get("exchange") or "").lower()
                if ":" in raw_sym:
                    ex_tv, sym_only = raw_sym.split(":", 1)
                    ex = (ex_tv or ex).lower()
                    raw_sym = sym_only
                out.append({
                    "symbol": raw_sym,
                    "exchange": ex,
                    "base": raw_sym,
                    "quote": "",
                    "display": raw_sym,
                    "description": row.get("description") or "",
                    "type": row.get("type") or "",
                    "is_active": True,
                })
                if len(out) >= limit:
                    break
            return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("tradingview search failed: %s", exc)
        return []


@router.get("", response_model=list[SymbolOut])
async def list_symbols(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
):
    rows = db.execute(
        select(SymbolMeta).where(SymbolMeta.is_active.is_(True)).order_by(SymbolMeta.symbol)
    ).scalars().all()
    if rows:
        return [
            SymbolOut(
                symbol=r.symbol, exchange=r.exchange, base=r.base, quote=r.quote,
                is_active=r.is_active,
            )
            for r in rows
        ]
    pairs = await _binance_pairs()
    return [
        SymbolOut(
            symbol=p["symbol"], exchange=p["exchange"],
            base=p["base"], quote=p["quote"],
            is_active=True,
            price=p.get("price"),
            change_24h_pct=p.get("change_24h_pct"),
            volume_24h_quote=p.get("volume_24h_quote"),
            display=p.get("display"),
        )
        for p in pairs[:200]
    ]


@router.get("/venues")
def venues(_user=Depends(get_current_user)):
    return _live_venues()


@router.get("/search", response_model=list[SymbolOut])
async def search_symbols(
    q: str = Query("", description="Search query"),
    limit: int = Query(75, ge=1, le=250),
    _user=Depends(get_current_user),
):
    """Combined search: Binance spot pairs (real-time) + TradingView catalog."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    q_lower = (q or "").lower().strip()

    binance_pairs = await _binance_pairs()
    for p in binance_pairs:
        if q_lower and q_lower not in p["display"].lower() and q_lower not in p["symbol"].lower():
            continue
        key = f"binance:{p['symbol']}"
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    tv_results = await _tradingview_results(q, limit=limit)
    for p in tv_results:
        key = f"{p['exchange']}:{p['symbol']}"
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    out.sort(key=lambda x: -(x.get("volume_24h_quote") or 0))
    return [SymbolOut(**p) for p in out[:limit]]


@router.get("/tv-catalog")
async def tv_catalog(q: str = Query(""), limit: int = Query(100, ge=1, le=500)):
    """Direct TradingView public catalog search — no auth, no key."""
    if not q:
        q = "BTC"
    results = await _tradingview_results(q, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/spot-pairs")
async def spot_pairs(venue: str = Query("binance"), limit: int = Query(50, ge=1, le=500)):
    """Live Binance spot pair snapshot, ranked by 24h volume."""
    venue = (venue or "binance").lower()
    if venue != "binance":
        return {"venue": venue, "pairs": []}
    pairs = await _binance_pairs()
    return {"venue": "binance", "pairs": pairs[:limit]}


@router.post("/sync")
async def sync_symbols(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
):
    """Refresh the local symbol_meta table from live Binance spot pairs."""
    pairs = await _binance_pairs()
    now_utc = datetime.now(timezone.utc)
    synced = 0
    for p in pairs:
        existing = db.execute(
            select(SymbolMeta).where(
                SymbolMeta.symbol == p["symbol"], SymbolMeta.exchange == p["exchange"]
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(SymbolMeta(
                symbol=p["symbol"], exchange=p["exchange"],
                base=p["base"], quote=p["quote"],
                is_active=True, last_synced=now_utc,
            ))
            synced += 1
        else:
            existing.is_active = True
            existing.last_synced = now_utc
    db.commit()
    return {"synced": synced, "total_pairs": len(pairs)}


__all__ = ["router"]

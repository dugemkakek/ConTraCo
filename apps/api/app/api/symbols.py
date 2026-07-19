"""Symbol metadata + universe listing API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import SymbolMeta, User
from app.services.market_data.factory import build_provider
from app.services.market_data.gateio_rest import GateioRestProvider

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


class SymbolOut(BaseModel):
    symbol: str
    exchange: str
    base: str
    quote: str
    is_active: bool
    tick_size: float | None
    min_qty: float | None


@router.get("", response_model=list[SymbolOut])
def list_symbols(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
    active_only: bool = True,
):
    stmt = select(SymbolMeta).order_by(SymbolMeta.symbol)
    if active_only:
        stmt = stmt.where(SymbolMeta.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    if rows:
        return [
            SymbolOut(
                symbol=r.symbol, exchange=r.exchange, base=r.base, quote=r.quote,
                is_active=r.is_active, tick_size=r.tick_size, min_qty=r.min_qty,
            )
            for r in rows
        ]
    # Fresh DB — return the provider's universe as ephemeral entries.
    provider = build_provider()
    return [
        SymbolOut(
            symbol=s, exchange=provider.name, base=s.split("/")[0], quote=s.split("/")[1],
            is_active=True, tick_size=None, min_qty=None,
        )
        for s in provider.supported_symbols()
    ]


@router.post("/sync")
async def sync_symbols(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Pull the live Gate.io spot pair list into ``symbol_meta`` if
    the live provider is configured. With mock, this is a no-op."""
    provider = build_provider()
    if not isinstance(provider, GateioRestProvider):
        return {"synced": 0, "note": "non-live provider; no sync needed"}
    try:
        pairs = await provider.list_spot_pairs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"gate.io sync failed: {exc}")
    now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    synced = 0
    for p in pairs:
        symbol = f"{p.get('base')}/{p.get('quote')}"
        if not p.get("trade_status") == "tradable":
            continue
        existing = db.execute(
            select(SymbolMeta).where(
                SymbolMeta.symbol == symbol, SymbolMeta.exchange == "gateio"
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(SymbolMeta(
                symbol=symbol, exchange="gateio",
                base=p.get("base", ""), quote=p.get("quote", ""),
                tick_size=p.get("precision"), min_qty=p.get("min_quote_amount"),
                is_active=True, last_synced=now_utc,
            ))
            synced += 1
        else:
            existing.is_active = True
            existing.last_synced = now_utc
    db.commit()
    return {"synced": synced, "total_pairs": len(pairs)}


@router.get("/venues", response_model=list[dict[str, str | bool]])
def list_venues_endpoint(_user=Depends(get_current_user)):
    from app.services.market_data.registry import list_venues
    return list_venues()


@router.get("/search", response_model=list[SymbolOut])
def search_symbols(
    q: str = Query(..., min_length=1),
    _user=Depends(get_current_user),
):
    from app.services.market_data.registry import all_providers
    results: list[SymbolOut] = []
    seen: set[str] = set()
    for provider in all_providers():
        for sym in provider.supported_symbols():
            if q.upper() in sym.upper() and sym not in seen:
                seen.add(sym)
                results.append(SymbolOut(
                    symbol=sym, exchange=provider.venue_id,
                    base=sym.split("/")[0], quote=sym.split("/")[1],
                    is_active=True, tick_size=None, min_qty=None,
                ))
    return results[:50]


__all__ = ["router"]

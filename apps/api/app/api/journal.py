"""Journal API.

Manual entries (trades the user took outside the system) and
entries auto-created from an analysis run / order.
"""


from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import JournalEntry, User

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


class JournalEntryIn(BaseModel):
    symbol: str
    side: str = Field(pattern=r"^(LONG|SHORT)$")
    entry_price: float
    exit_price: float | None = None
    qty: float
    opened_at: datetime
    closed_at: datetime | None = None
    notes: str = ""
    analysis_run_id: int | None = None
    order_id: int | None = None


class JournalEntryOut(BaseModel):
    id: int
    symbol: str
    side: str
    entry_price: float
    exit_price: float | None
    qty: float
    opened_at: str
    closed_at: str | None
    pnl: float | None
    notes: str
    analysis_run_id: int | None
    order_id: int | None
    created_at: str


def _serialize(e: JournalEntry) -> JournalEntryOut:
    return JournalEntryOut(
        id=e.id, symbol=e.symbol, side=e.side, entry_price=e.entry_price,
        exit_price=e.exit_price, qty=e.qty,
        opened_at=e.opened_at.isoformat(),
        closed_at=e.closed_at.isoformat() if e.closed_at else None,
        pnl=e.pnl, notes=e.notes,
        analysis_run_id=e.analysis_run_id, order_id=e.order_id,
        created_at=e.created_at.isoformat(),
    )


def compute_pnl(side: str, entry: float, exit_: float | None, qty: float) -> float | None:
    if exit_ is None:
        return None
    diff = (exit_ - entry) * qty
    return diff if side == "LONG" else -diff


@router.get("", response_model=list[JournalEntryOut])
def list_entries(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str | None = None,
    open_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(
        desc(JournalEntry.opened_at)
    ).limit(limit).offset(offset)
    if symbol:
        stmt = stmt.where(JournalEntry.symbol == symbol.upper())
    if open_only:
        stmt = stmt.where(JournalEntry.closed_at.is_(None))
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=JournalEntryOut, status_code=201)
def create_entry(
    body: JournalEntryIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    e = JournalEntry(
        user_id=user.id,
        symbol=body.symbol.upper(),
        side=body.side,
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        qty=body.qty,
        opened_at=body.opened_at if body.opened_at.tzinfo else body.opened_at.replace(tzinfo=timezone.utc),
        closed_at=body.closed_at,
        pnl=compute_pnl(body.side, body.entry_price, body.exit_price, body.qty),
        notes=body.notes,
        analysis_run_id=body.analysis_run_id,
        order_id=body.order_id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _serialize(e)


@router.patch("/{entry_id}", response_model=JournalEntryOut)
def update_entry(
    entry_id: int,
    body: JournalEntryIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    e = db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(status_code=404, detail="entry not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "pnl":
            continue
        setattr(e, k, v)
    e.pnl = compute_pnl(e.side, e.entry_price, e.exit_price, e.qty)
    db.commit()
    db.refresh(e)
    return _serialize(e)


@router.post("/{entry_id}/close", response_model=JournalEntryOut)
def close_entry(
    entry_id: int,
    body: dict,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    e = db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(status_code=404, detail="entry not found")
    if "exit_price" not in body:
        raise HTTPException(status_code=400, detail="exit_price required")
    e.exit_price = float(body["exit_price"])
    e.closed_at = datetime.now(timezone.utc)
    e.pnl = compute_pnl(e.side, e.entry_price, e.exit_price, e.qty)
    if "notes" in body:
        e.notes = body["notes"]
    db.commit()
    db.refresh(e)
    return _serialize(e)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    e = db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(status_code=404, detail="entry not found")
    db.delete(e)
    db.commit()
    return None


@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    rows = db.execute(
        select(JournalEntry).where(JournalEntry.user_id == user.id)
    ).scalars().all()
    closed = [r for r in rows if r.pnl is not None]
    return {
        "total_entries": len(rows),
        "open_entries": len(rows) - len(closed),
        "closed_entries": len(closed),
        "total_pnl": round(sum(r.pnl for r in closed), 4),
        "winners": sum(1 for r in closed if r.pnl > 0),
        "losers": sum(1 for r in closed if r.pnl < 0),
    }


__all__ = ["router"]

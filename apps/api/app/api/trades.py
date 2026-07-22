"""Trade execution API."""


from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import JournalEntry, Order, OrderStatus, User
from app.services.execution import LIVE_TRADING, OrderRequest, execute_order

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


class OrderRequestIn(BaseModel):
    symbol: str
    side: str
    order_type: str = "MARKET"
    qty: float
    price: float | None = None
    analysis_run_id: int | None = None
    auto_journal: bool = True


class OrderOut(BaseModel):
    id: int
    exchange: str
    symbol: str
    side: str
    order_type: str
    qty: float
    price: float | None
    status: str
    exchange_order_id: str | None
    created_at: str
    submitted_at: str | None
    filled_at: str | None
    raw_response: dict
    error: str | None = None


def _serialize(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id, exchange=o.exchange, symbol=o.symbol, side=o.side,
        order_type=o.order_type, qty=o.qty, price=o.price,
        status=o.status.value, exchange_order_id=o.exchange_order_id,
        created_at=o.created_at.isoformat(),
        submitted_at=o.submitted_at.isoformat() if o.submitted_at else None,
        filled_at=o.filled_at.isoformat() if o.filled_at else None,
        raw_response=o.raw_response,
    )


@router.get("/config")
def config(user: Annotated[User, Depends(get_current_user)]):
    """Tell the UI whether live trading is on (so the button can
    label itself correctly and refuse where appropriate)."""
    return {
        "live_trading": LIVE_TRADING,
        "max_notional_usd": float(__import__("os").getenv("MAX_ORDER_NOTIONAL_USD", "1000")),
    }


@router.post("/orders", response_model=OrderOut)
async def post_order(
    body: OrderRequestIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if body.order_type not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail="order_type must be MARKET or LIMIT")
    if body.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    if body.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")
    if body.order_type == "LIMIT" and (body.price is None or body.price <= 0):
        raise HTTPException(status_code=400, detail="LIMIT orders require a positive price")

    req = OrderRequest(
        symbol=body.symbol.upper(), side=body.side,
        order_type=body.order_type, qty=body.qty, price=body.price,
        analysis_run_id=body.analysis_run_id,
    )
    result = await execute_order(req, user.id)
    order = Order(
        user_id=user.id,
        run_id=body.analysis_run_id,
        exchange="gateio",
        symbol=body.symbol.upper(),
        side=body.side,
        order_type=body.order_type,
        qty=body.qty,
        price=body.price,
        status=result.status,
        exchange_order_id=result.exchange_order_id,
        submitted_at=result.submitted_at,
        filled_at=result.filled_at,
        raw_response=result.raw_response,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    if body.auto_journal and result.status == OrderStatus.FILLED:
        side = "LONG" if body.side == "BUY" else "SHORT"
        db.add(
            JournalEntry(
                user_id=user.id,
                symbol=body.symbol.upper(),
                side=side,
                entry_price=result.filled_price or body.price or 0.0,
                qty=result.filled_qty or body.qty,
                opened_at=result.filled_at or datetime.now(timezone.utc),
                notes=f"auto-created from order {order.id}",
                order_id=order.id,
                analysis_run_id=body.analysis_run_id,
            )
        )
        db.commit()
    return _serialize(order)


@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = db.execute(
        select(Order).where(Order.user_id == user.id).order_by(desc(Order.created_at))
        .limit(limit).offset(offset)
    ).scalars().all()
    return [_serialize(o) for o in rows]


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    o = db.get(Order, order_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(status_code=404, detail="order not found")
    return _serialize(o)


__all__ = ["router"]

"""Order execution interface — RECOMMEND-ONLY.

This module provides PAPER execution for testing and an opt-in live
Gate.io execution path gated by explicit credentials and the
``LIVE_TRADING=1`` environment variable.

There is no DEX execution path in this project. DEX integration
(`app/services/market_data/dex.py`) provides read-only pool data,
quotes, and tranche discovery — no transaction construction, no
signing, no wallet interaction. That boundary is enforced by
``scripts/check_boundaries.py``.

When paper mode is on, fills are clearly marked
``exchange_order_id="paper-{ts}"`` so downstream consumers can
distinguish from real exchange fills.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.db.models import Order, OrderStatus

logger = logging.getLogger(__name__)

GATEIO_REST = "https://api.gateio.ws/api/v4"
LIVE_TRADING = os.getenv("LIVE_TRADING", "0") == "1"
MAX_NOTIONAL_USD = float(os.getenv("MAX_ORDER_NOTIONAL_USD", "1000"))


@dataclass
class OrderRequest:
    symbol: str  # "BTC/USDT"
    side: str  # "BUY" / "SELL"
    order_type: str = "MARKET"  # MARKET / LIMIT
    qty: float = 0.0
    price: float | None = None
    analysis_run_id: int | None = None


@dataclass
class OrderResult:
    status: OrderStatus
    exchange_order_id: str | None
    submitted_at: datetime | None
    filled_at: datetime | None
    filled_qty: float
    filled_price: float | None
    raw_response: dict
    error: str | None = None


def _gateio_pair(symbol: str) -> str:
    return symbol.replace("/", "_").upper()


def _sign(secret: str, method: str, path: str, query: str, body: str) -> dict[str, str]:
    ts = str(int(time.time()))
    hashed = hashlib.sha512(body.encode("utf-8")).hexdigest()
    s = f"{method}\n{path}\n{query}\n{hashed}\n{ts}"
    sig = hmac.new(secret.encode("utf-8"), s.encode("utf-8"), hashlib.sha512).hexdigest()
    return {
        "KEY": os.getenv("GATEIO_API_KEY", ""),
        "SIGN": sig,
        "Timestamp": ts,
    }


async def execute_order(req: OrderRequest, user_id: int) -> OrderResult:
    """Submit an order. Paper by default; live when ``LIVE_TRADING=1``."""
    notional = req.qty * (req.price or 0)
    if req.order_type != "LIMIT" and notional <= 0:
        # Market order with no reference price: refuse.
        return OrderResult(
            status=OrderStatus.REJECTED,
            exchange_order_id=None, submitted_at=None, filled_at=None,
            filled_qty=0.0, filled_price=None,
            raw_response={"reason": "market orders require a reference price"},
            error="reference price required for market order notional check",
        )
    if notional > MAX_NOTIONAL_USD:
        return OrderResult(
            status=OrderStatus.REJECTED,
            exchange_order_id=None, submitted_at=None, filled_at=None,
            filled_qty=0.0, filled_price=None,
            raw_response={"reason": f"notional ${notional:.2f} > cap ${MAX_NOTIONAL_USD:.2f}"},
            error="notional cap exceeded",
        )

    if not LIVE_TRADING:
        # Paper execution: synthesize a fill at the requested price
        # (or 0 for market, which the caller should treat as a placeholder).
        now = datetime.now(timezone.utc)
        return OrderResult(
            status=OrderStatus.FILLED,
            exchange_order_id=f"paper-{int(now.timestamp() * 1000)}",
            submitted_at=now, filled_at=now,
            filled_qty=req.qty,
            filled_price=req.price,
            raw_response={"mode": "paper", "request": req.__dict__},
        )

    # Live execution: sign + POST to Gate.io.
    api_key = os.getenv("GATEIO_API_KEY", "")
    api_secret = os.getenv("GATEIO_API_SECRET", "")
    if not api_key or not api_secret:
        return OrderResult(
            status=OrderStatus.REJECTED, exchange_order_id=None,
            submitted_at=None, filled_at=None, filled_qty=0.0, filled_price=None,
            raw_response={"reason": "GATEIO_API_KEY / GATEIO_API_SECRET not set"},
            error="missing API credentials",
        )

    pair = _gateio_pair(req.symbol)
    body = {
        "currency_pair": pair,
        "side": req.side.lower(),
        "type": req.order_type.lower(),
        "amount": str(req.qty),
    }
    if req.price is not None:
        body["price"] = str(req.price)
    body_str = json.dumps(body, separators=(",", ":"))
    path = "/spot/orders"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **_sign(api_secret, "POST", path, "", body_str),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{GATEIO_REST}{path}", content=body_str, headers=headers)
    raw = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"text": resp.text}
    if resp.status_code >= 400:
        return OrderResult(
            status=OrderStatus.REJECTED, exchange_order_id=None,
            submitted_at=None, filled_at=None, filled_qty=0.0, filled_price=None,
            raw_response=raw, error=f"gate.io {resp.status_code}",
        )
    eoid = str(raw.get("id", "")) or None
    status_str = (raw.get("status") or "").upper()
    status_enum = {
        "OPEN": OrderStatus.SUBMITTED,
        "CLOSED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELED,
        "REJECTED": OrderStatus.REJECTED,
    }.get(status_str, OrderStatus.SUBMITTED)
    filled = float(raw.get("filled_amount", 0) or 0)
    avg_price = float(raw.get("avg_deal_price", 0) or 0) or None
    return OrderResult(
        status=status_enum,
        exchange_order_id=eoid,
        submitted_at=datetime.now(timezone.utc),
        filled_at=datetime.now(timezone.utc) if status_enum == OrderStatus.FILLED else None,
        filled_qty=filled,
        filled_price=avg_price,
        raw_response=raw,
    )


__all__ = ["execute_order", "OrderRequest", "OrderResult", "LIVE_TRADING"]

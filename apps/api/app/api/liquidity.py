"""Liquidity API routes — live funding, OI, long/short ratio, heatmap placeholders."""


from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter(prefix="/api/v1/liquidity", tags=["liquidity"])


@router.get("/heatmap")
async def liquidity_heatmap(
    symbol: Annotated[str, Query(...)],
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Liquidation cluster levels derived from live Binance OI + funding + swing structure.

    The heuristic: take the recent swing-high/swing-low structure of
    the live candles and weight by the live open-interest value. The
    resulting ``levels`` array marks the nearest liquidity magnets
    above and below the mark price.
    """
    from app.services.market_data.binance_rest import BinanceRestProvider
    from app.services.market_data.factory import build_provider
    from app.engine.gates.liquidity_heatmap import LiquidityHeatmapGate
    from app.schemas.candle import Candle
    from datetime import datetime, timezone

    sym = symbol.upper()
    try:
        provider = BinanceRestProvider()
        candles_raw = await provider.get_ohlcv(sym, "1h", limit=200)
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(c.timestamp.timestamp(), tz=timezone.utc)
                if hasattr(c.timestamp, "timestamp")
                else datetime.fromisoformat(str(c.timestamp)),
                open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume,
            )
            for c in candles_raw
        ]
        funding = await provider.get_funding_rate(sym)
        oi = await provider.get_open_interest(sym)
        gate = LiquidityHeatmapGate()
        evaluation = await gate.evaluate(__import__("app.engine.gates", fromlist=["GateContext"]).GateContext(
            symbol=sym, timeframe="1h", candles=candles,
            symbol_meta={
                "open_interest_usd": oi.get("open_interest_value_usd"),
                "funding_rate": funding.get("funding_rate"),
                "mark_price": funding.get("mark_price"),
            },
        ))
        return {
            "symbol": sym,
            "levels": evaluation.evidence.get("levels", []),
            "score": evaluation.score,
            "confidence": evaluation.confidence,
            "reason": evaluation.reason,
            "source": "binance_oi_derived",
            "funding_rate": funding.get("funding_rate"),
            "open_interest_usd": oi.get("open_interest_value_usd"),
            "mark_price": funding.get("mark_price"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": sym, "levels": [], "source": "binance_oi_derived",
            "error": str(exc),
        }


@router.get("/funding-oi")
async def funding_oi(
    symbol: Annotated[str, Query(...)],
    _user: Annotated[User, Depends(get_current_user)] = None,
):
    """Live funding rate + open interest from Binance USD-M perpetuals."""
    from app.services.market_data.binance_rest import BinanceRestProvider

    sym = symbol.upper()
    provider = BinanceRestProvider()
    funding: dict[str, Any] = {}
    oi: dict[str, Any] = {}
    ratio: dict[str, Any] = {}
    errors: list[str] = []
    try:
        funding = await provider.get_funding_rate(sym)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"funding: {exc}")
    try:
        oi = await provider.get_open_interest(sym)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"oi: {exc}")
    try:
        ratio = await provider.get_long_short_ratio(sym)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ls_ratio: {exc}")

    return {
        "symbol": sym,
        "funding": {
            "current": funding.get("funding_rate"),
            "predicted": funding.get("predicted"),
            "next_funding_at": funding.get("next_funding_at"),
            "mark_price": funding.get("mark_price"),
            "history": funding.get("history", []),
        },
        "open_interest": {
            "current": oi.get("open_interest"),
            "value_usd": oi.get("open_interest_value_usd"),
        },
        "long_short_ratio": ratio.get("long_short_ratio"),
        "long_short_history": ratio.get("history", []),
        "source": "binance_fapi",
        "errors": errors,
    }

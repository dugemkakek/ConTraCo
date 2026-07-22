"""Backtest API — CRUD + run endpoint for BacktestRun model."""


import logging
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import BacktestRun, HistoricalCandle, User
from app.engine.confluence_backtest import BacktestConfig, run_backtest as run_confluence_backtest
from app.engine.strategy import get_active_spec
from app.schemas.candle import Candle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

BINANCE_KLINES = "https://data-api.binance.vision/api/v3/klines"
BINANCE_INTERVALS = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}


async def _fetch_binance_candles(
    db: Session, symbol: str, timeframe: str,
    start: datetime, end: datetime,
) -> int:
    """Fetch candles from Binance and store in DB. Returns count inserted."""
    pair = symbol.replace("/", "").upper()
    interval = BINANCE_INTERVALS.get(timeframe, "1h")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    inserted = 0

    async with httpx.AsyncClient(timeout=15, verify=False) as client:
        cursor = start_ms
        while cursor < end_ms:
            try:
                resp = await client.get(BINANCE_KLINES, params={
                    "symbol": pair, "interval": interval,
                    "startTime": str(cursor), "endTime": str(end_ms),
                    "limit": "1000",
                })
                if resp.status_code != 200:
                    break
                rows = resp.json()
                if not rows:
                    break
                for k in rows:
                    ot = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
                    exists = db.execute(
                        select(HistoricalCandle.id)
                        .where(HistoricalCandle.symbol == symbol.upper())
                        .where(HistoricalCandle.venue == "binance")
                        .where(HistoricalCandle.timeframe == timeframe)
                        .where(HistoricalCandle.open_time == ot)
                    ).first()
                    if not exists:
                        db.add(HistoricalCandle(
                            symbol=symbol.upper(), venue="binance",
                            timeframe=timeframe, open_time=ot,
                            open=float(k[1]), high=float(k[2]),
                            low=float(k[3]), close=float(k[4]),
                            volume=float(k[5]),
                        ))
                        inserted += 1
                cursor = rows[-1][0] + 1  # next ms after last candle
                if len(rows) < 1000:
                    break
            except Exception as exc:
                logger.warning("binance klines fetch failed: %s", exc)
                break

    if inserted:
        db.commit()
    return inserted


class BacktestRunOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    strategy_id: int | None
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float | None
    status: str
    metrics: dict[str, Any] | None
    equity_curve: list[float] | None = None
    created_at: str


class BacktestRunIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    timeframe: str = Field(default="1h", pattern=r"^\d+[mhdw]$")
    strategy_id: int | None = None
    start_date: datetime
    end_date: datetime
    initial_balance: float = Field(default=10000.0, gt=0)
    commission_pct: float = Field(default=0.1, ge=0)
    slippage_pct: float = Field(default=0.05, ge=0)
    stop_loss_pct: float = Field(default=2.0, gt=0)
    take_profit_pct: float = Field(default=4.0, gt=0)
    lookback: int = Field(default=50, ge=10)


def _serialize(r: BacktestRun) -> BacktestRunOut:
    return BacktestRunOut(
        id=r.id, symbol=r.symbol, timeframe=r.timeframe,
        strategy_id=r.strategy_id,
        start_date=r.start_date.isoformat(),
        end_date=r.end_date.isoformat(),
        initial_balance=r.initial_balance,
        final_balance=r.final_balance,
        status=r.status,
        metrics=r.metrics_json,
        equity_curve=r.equity_curve_json,
        created_at=r.created_at.isoformat(),
    )


@router.get("", response_model=list[BacktestRunOut])
def list_runs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.user_id == user.id)
        .order_by(desc(BacktestRun.created_at))
        .limit(limit)
        .offset(offset)
    )
    if symbol:
        stmt = stmt.where(BacktestRun.symbol == symbol.upper())
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/{run_id}", response_model=BacktestRunOut)
def get_run(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    r = db.get(BacktestRun, run_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "backtest run not found")
    return _serialize(r)


@router.post("/run", response_model=BacktestRunOut, status_code=201)
async def create_and_run(
    body: BacktestRunIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Create a backtest run record, execute it against stored candles using
    the real 14-gate confluence engine, save results."""
    # Load historical candles
    candle_rows = db.execute(
        select(HistoricalCandle)
        .where(HistoricalCandle.symbol == body.symbol.upper())
        .where(HistoricalCandle.timeframe == body.timeframe)
        .where(HistoricalCandle.open_time >= body.start_date)
        .where(HistoricalCandle.open_time <= body.end_date)
        .order_by(HistoricalCandle.open_time)
    ).scalars().all()

    min_candles = 200 + 12 + 1  # WARMUP_BARS + holding_bars + 1
    if len(candle_rows) < min_candles:
        # Auto-fetch from Binance when DB is empty/insufficient
        start_dt = body.start_date if body.start_date.tzinfo else body.start_date.replace(tzinfo=timezone.utc)
        end_dt = body.end_date if body.end_date.tzinfo else body.end_date.replace(tzinfo=timezone.utc)
        fetched = await _fetch_binance_candles(db, body.symbol, body.timeframe, start_dt, end_dt)
        if fetched:
            candle_rows = db.execute(
                select(HistoricalCandle)
                .where(HistoricalCandle.symbol == body.symbol.upper())
                .where(HistoricalCandle.timeframe == body.timeframe)
                .where(HistoricalCandle.open_time >= body.start_date)
                .where(HistoricalCandle.open_time <= body.end_date)
                .order_by(HistoricalCandle.open_time)
            ).scalars().all()
        if len(candle_rows) < min_candles:
            raise HTTPException(
                400,
                f"insufficient candles: {len(candle_rows)} found (fetched {fetched} from Binance), need {min_candles}+",
            )

    candles = [
        Candle(
            timestamp=c.open_time,
            open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume,
        )
        for c in candle_rows
    ]

    # Load strategy spec (falls back to balanced preset on fresh DB)
    _, spec = get_active_spec(db)

    # Create DB record
    run = BacktestRun(
        user_id=user.id,
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
        strategy_id=body.strategy_id,
        start_date=body.start_date if body.start_date.tzinfo else body.start_date.replace(tzinfo=timezone.utc),
        end_date=body.end_date if body.end_date.tzinfo else body.end_date.replace(tzinfo=timezone.utc),
        initial_balance=body.initial_balance,
        status="RUNNING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        bt_config = BacktestConfig(
            initial_equity=body.initial_balance,
            fee_bps=body.commission_pct * 100,
            slippage_bps=body.slippage_pct * 100,
        )
        result = await run_confluence_backtest(
            symbol=body.symbol.upper(),
            timeframe=body.timeframe,
            candles=candles,
            spec=spec,
            config=bt_config,
        )
        result_dict = result.to_dict()
        run.final_balance = result_dict["metrics"]["final_equity"]
        run.status = "COMPLETED"
        run.metrics_json = {
            **result_dict["metrics"],
            "walk_forward": result_dict["walk_forward"],
            "per_gate_accuracy": result_dict["per_gate_accuracy"],
            "gate_version": result_dict["gate_version"],
        }
        run.equity_curve_json = [pt["equity"] for pt in result_dict["equity_curve"]]
    except Exception as exc:
        run.status = "FAILED"
        run.metrics_json = {"error": str(exc)}

    db.commit()
    db.refresh(run)
    return _serialize(run)


@router.delete("/{run_id}", status_code=204)
def delete_run(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    r = db.get(BacktestRun, run_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "backtest run not found")
    db.delete(r)
    db.commit()
    return None


__all__ = ["router"]

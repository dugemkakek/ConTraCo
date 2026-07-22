"""Risk API — risk-of-ruin, portfolio exposure, P&L attribution by gate."""


from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import User
from app.engine.risk.risk_of_ruin import calculate_risk_of_ruin, calculate_portfolio_exposure
from app.engine.risk.pnl_attribution import compute_gate_attribution

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


class RiskOfRuinIn(BaseModel):
    win_rate: float = Field(ge=0, le=1)
    avg_win: float = Field(gt=0)
    avg_loss: float = Field(gt=0)
    bankroll: float = Field(gt=0)
    unit_size: float = Field(gt=0)


class ExposurePositionIn(BaseModel):
    symbol: str
    side: str = "LONG"
    qty: float = 0
    entry_price: float = 0
    notional: float = 0


class ExposureIn(BaseModel):
    positions: list[ExposurePositionIn]
    equity: float = Field(gt=0)
    cap_pct: float = Field(default=100.0, gt=0)


@router.post("/risk-of-ruin")
def risk_of_ruin(body: RiskOfRuinIn):
    result = calculate_risk_of_ruin(
        win_rate=body.win_rate,
        avg_win=body.avg_win,
        avg_loss=body.avg_loss,
        bankroll=body.bankroll,
        unit_size=body.unit_size,
    )
    return {
        "risk_of_ruin_pct": result.risk_of_ruin_pct,
        "edge": result.edge,
        "win_rate": result.win_rate,
        "win_loss_ratio": result.win_loss_ratio,
        "bankroll": result.bankroll,
        "unit_size": result.unit_size,
        "note": result.note,
    }


@router.post("/exposure")
def portfolio_exposure(body: ExposureIn):
    result = calculate_portfolio_exposure(
        positions=[p.model_dump() for p in body.positions],
        equity=body.equity,
        cap_pct=body.cap_pct,
    )
    return {
        "total_notional": result.total_notional,
        "total_pct": result.total_pct,
        "equity": result.equity,
        "long_pct": result.long_pct,
        "short_pct": result.short_pct,
        "net_pct": result.net_pct,
        "breached": result.breached,
        "cap_pct": result.cap_pct,
        "positions": [
            {"symbol": p.symbol, "side": p.side, "notional": p.notional, "pct_of_equity": p.pct_of_equity}
            for p in result.positions
        ],
    }


@router.get("/attribution")
def gate_attribution(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 500,
):
    report = compute_gate_attribution(db, user.id, limit=limit)
    return {
        "total_closed_trades": report.total_closed_trades,
        "total_pnl": report.total_pnl,
        "gates": [
            {
                "gate_name": g.gate_name,
                "total_trades": g.total_trades,
                "correct_calls": g.correct_calls,
                "accuracy_pct": g.accuracy_pct,
                "avg_confidence": g.avg_confidence,
                "pnl_when_correct": g.pnl_when_correct,
                "pnl_when_wrong": g.pnl_when_wrong,
            }
            for g in report.gates
        ],
    }


__all__ = ["router"]

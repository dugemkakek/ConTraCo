"""Analytics API routes — trade performance, equity, by-symbol, by-time."""


from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import User
from app.services.analytics.trade_analytics import compute_overview

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
def analytics_overview(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stats = compute_overview(db, _user.id)
    return {
        "total_trades": stats.total_trades,
        "win_rate": stats.win_rate,
        "total_pnl": stats.total_pnl,
        "profit_factor": stats.profit_factor,
        "expectancy": stats.expectancy,
        "sharpe_ratio": stats.sharpe_ratio,
        "max_drawdown": stats.max_drawdown,
        "largest_win": stats.largest_win,
        "largest_loss": stats.largest_loss,
        "consecutive_wins": stats.consecutive_wins,
        "consecutive_losses": stats.consecutive_losses,
    }


@router.get("/equity-curve")
def equity_curve(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stats = compute_overview(db, _user.id)
    return {"equity": stats.equity_curve, "total_pnl": stats.total_pnl}


@router.get("/by-symbol")
def by_symbol(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stats = compute_overview(db, _user.id)
    return {"symbols": stats.by_symbol}


@router.get("/by-hour")
def by_hour(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stats = compute_overview(db, _user.id)
    return {"hourly": stats.by_hour}


@router.get("/monthly-returns")
def monthly_returns(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stats = compute_overview(db, _user.id)
    return {"monthly": stats.monthly_returns}

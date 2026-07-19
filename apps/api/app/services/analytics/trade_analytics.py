"""Trade analytics — per-trade, per-strategy, per-symbol, time-based."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from app.db.models import JournalEntry


@dataclass
class TradeAnalytics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    avg_trade_duration_hours: float = 0.0
    total_return_pct: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    monthly_returns: dict[str, float] = field(default_factory=dict)
    by_symbol: list[dict[str, Any]] = field(default_factory=list)
    by_strategy: list[dict[str, Any]] = field(default_factory=list)
    by_hour: dict[int, float] = field(default_factory=dict)
    streaks: list[int] = field(default_factory=list)


def compute_overview(db: Session, user_id: int) -> TradeAnalytics:
    """Compute comprehensive trade analytics from the journal."""
    entries = db.execute(
        select(JournalEntry)
        .where(JournalEntry.user_id == user_id)
        .where(JournalEntry.pnl.isnot(None))
        .order_by(JournalEntry.closed_at)
    ).scalars().all()

    if not entries:
        return TradeAnalytics()

    pnls = [e.pnl for e in entries if e.pnl is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_trades = len(pnls)
    win_count = len(wins)
    loss_count = len(losses)
    total_pnl = sum(pnls)
    win_rate = win_count / total_trades if total_trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses)) / len(losses) if losses else 0

    # Profit factor
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss else 0

    # Expectancy
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss) if avg_loss else 0

    # Equity curve (cumulative PnL)
    equity = 0.0
    curve: list[float] = []
    for p in pnls:
        equity += p
        curve.append(equity)

    # Max drawdown
    peak = float("-inf")
    dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = min(dd, v - peak)
    max_dd = abs(dd)

    # Sharpe (simplified, assuming risk-free rate = 0)
    returns = pnls  # simplified
    if len(returns) > 1:
        avg_r = sum(returns) / len(returns)
        variance = sum((r - avg_r) ** 2 for r in returns) / len(returns)
        sharpe = (avg_r / math.sqrt(variance)) * math.sqrt(252) if variance > 0 else 0
    else:
        sharpe = 0

    # Streaks
    current_streak = 1
    max_streak = 1
    for i in range(1, len(pnls)):
        if (pnls[i] > 0) == (pnls[i - 1] > 0):
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1
    consecutive_wins = max_streak if pnls and pnls[-1] > 0 else 0
    consecutive_losses = max_streak if pnls and pnls[-1] < 0 else 0

    # By symbol
    symbols = set(e.symbol for e in entries)
    by_sym = []
    for sym in symbols:
        sym_pnls = [e.pnl for e in entries if e.symbol == sym and e.pnl is not None]
        by_sym.append({
            "symbol": sym,
            "trades": len(sym_pnls),
            "pnl": sum(sym_pnls),
            "wins": len([p for p in sym_pnls if p > 0]),
        })

    # By hour
    by_hour: dict[int, float] = {}
    for e in entries:
        if e.closed_at and e.pnl is not None:
            h = e.closed_at.hour
            by_hour[h] = by_hour.get(h, 0) + e.pnl

    # Monthly returns
    monthly: dict[str, float] = {}
    for e in entries:
        if e.closed_at and e.pnl is not None:
            month_key = e.closed_at.strftime("%Y-%m")
            monthly[month_key] = monthly.get(month_key, 0) + e.pnl

    return TradeAnalytics(
        total_trades=total_trades,
        wins=win_count, losses=loss_count,
        win_rate=round(win_rate, 4),
        total_pnl=round(total_pnl, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2),
        expectancy=round(expectancy, 2),
        sharpe_ratio=round(sharpe, 2),
        max_drawdown=round(max_dd, 2),
        largest_win=round(max(wins), 2) if wins else 0,
        largest_loss=round(min(losses), 2) if losses else 0,
        consecutive_wins=consecutive_wins,
        consecutive_losses=consecutive_losses,
        equity_curve=[round(v, 2) for v in curve],
        monthly_returns={k: round(v, 2) for k, v in monthly.items()},
        by_symbol=sorted(by_sym, key=lambda x: -x["pnl"]),
        by_hour={k: round(v, 2) for k, v in sorted(by_hour.items())},
    )

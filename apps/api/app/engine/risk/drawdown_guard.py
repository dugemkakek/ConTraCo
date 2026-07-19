"""Drawdown guard — circuit breakers based on daily/weekly losses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import JournalEntry


@dataclass
class DrawdownStatus:
    level: str  # "green" | "yellow" | "red"
    daily_pnl: float
    weekly_pnl: float
    consecutive_losses: int
    message: str = ""


async def check_drawdown(
    db: Session,
    user_id: int,
    daily_max_loss_pct: float = 3.0,
    weekly_max_loss_pct: float = 6.0,
    max_consecutive_losses: int = 3,
) -> DrawdownStatus:
    """Check if drawdown limits are breached."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    # Daily PnL (closed trades)
    daily_pnl = db.execute(
        select(func.coalesce(func.sum(JournalEntry.pnl), 0.0))
        .where(JournalEntry.user_id == user_id)
        .where(JournalEntry.closed_at >= day_ago)
        .where(JournalEntry.pnl.isnot(None))
    ).scalar() or 0.0

    # Weekly PnL
    weekly_pnl = db.execute(
        select(func.coalesce(func.sum(JournalEntry.pnl), 0.0))
        .where(JournalEntry.user_id == user_id)
        .where(JournalEntry.closed_at >= week_ago)
        .where(JournalEntry.pnl.isnot(None))
    ).scalar() or 0.0

    # Consecutive losses
    recent = db.execute(
        select(JournalEntry.pnl)
        .where(JournalEntry.user_id == user_id)
        .where(JournalEntry.closed_at.isnot(None))
        .where(JournalEntry.pnl.isnot(None))
        .order_by(JournalEntry.closed_at.desc())
        .limit(max_consecutive_losses + 5)
    ).scalars().all()

    streak = 0
    for pnl in recent:
        if pnl and pnl < 0:
            streak += 1
        else:
            break

    # Determine level (assume $10k equity for pct calc; real calc needs account balance)
    # Simplified: absolute thresholds for demo
    daily_loss_pct = abs(daily_pnl) / 100.0
    weekly_loss_pct = abs(weekly_pnl) / 100.0

    if daily_loss_pct >= daily_max_loss_pct or weekly_loss_pct >= weekly_max_loss_pct:
        return DrawdownStatus("red", daily_pnl, weekly_pnl, streak,
                              f"Daily loss {daily_loss_pct:.1f}% >= {daily_max_loss_pct}% — CIRCUIT BREAKER")
    if streak >= max_consecutive_losses:
        return DrawdownStatus("yellow", daily_pnl, weekly_pnl, streak,
                              f"{streak} consecutive losses — cooldown recommended")
    if daily_loss_pct >= daily_max_loss_pct * 0.7:
        return DrawdownStatus("yellow", daily_pnl, weekly_pnl, streak,
                              "Approaching daily loss limit")

    return DrawdownStatus("green", daily_pnl, weekly_pnl, streak, "All clear")

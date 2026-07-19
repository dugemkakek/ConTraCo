"""Backtesting engine — historical simulation, metrics, walk-forward."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.schemas.candle import Candle

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    avg_trade_duration: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    total_return: float = 0.0
    annualized_return: float = 0.0
    calmar_ratio: float = 0.0
    equity_curve: list[float] = field(default_factory=list)


async def run_backtest(
    candles: list[Candle],
    signal_fn: Callable,
    initial_balance: float = 10000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    lookback: int = 50,
) -> BacktestMetrics:
    """Run a backtest over historical candles using a signal function."""
    if len(candles) < lookback + 10:
        return BacktestMetrics()

    balance = initial_balance
    equity_curve: list[float] = [balance]
    trades: list[dict[str, Any]] = []

    in_position = False
    position: dict[str, Any] = {}

    for i in range(lookback, len(candles)):
        window = candles[i - lookback : i]
        current = candles[i]

        # Generate signal from the window
        signal = await signal_fn(window)

        if not in_position and signal.get("action") in ("BUY", "SELL"):
            entry_price = float(current.open) * (1 + slippage_pct / 100)
            side = signal["action"]
            stop = entry_price * (1 - stop_loss_pct / 100) if side == "BUY" else entry_price * (1 + stop_loss_pct / 100)
            tp = entry_price * (1 + take_profit_pct / 100) if side == "BUY" else entry_price * (1 - take_profit_pct / 100)

            position = {
                "side": side,
                "entry": entry_price,
                "stop": stop,
                "tp": tp,
                "entry_idx": i,
                "size": 0.0,
                "commission": 0.0,
            }
            in_position = True

        elif in_position and current is not None:
            price = float(current.close)
            pnl = 0.0

            # Check stop loss / take profit
            if position["side"] == "BUY":
                if price <= position["stop"]:
                    pnl = (position["stop"] - position["entry"]) / position["entry"]
                    trades.append({**position, "exit": position["stop"], "pnl": pnl, "reason": "SL"})
                    in_position = False
                elif price >= position["tp"]:
                    pnl = (position["tp"] - position["entry"]) / position["entry"]
                    trades.append({**position, "exit": position["tp"], "pnl": pnl, "reason": "TP"})
                    in_position = False
            else:  # SHORT
                if price >= position["stop"]:
                    pnl = (position["entry"] - position["stop"]) / position["entry"]
                    trades.append({**position, "exit": position["stop"], "pnl": pnl, "reason": "SL"})
                    in_position = False
                elif price <= position["tp"]:
                    pnl = (position["entry"] - position["tp"]) / position["entry"]
                    trades.append({**position, "exit": position["tp"], "pnl": pnl, "reason": "TP"})
                    in_position = False

            if not in_position:
                balance *= (1 + pnl)
                balance -= abs(balance * commission_pct / 100)

        equity_curve.append(balance)

    # Calculate metrics
    if not trades:
        return BacktestMetrics(equity_curve=[initial_balance, balance])

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
    expectancy = (win_rate * (sum(wins) / len(wins) if wins else 0)
                  - (1 - win_rate) * (abs(sum(losses)) / len(losses) if losses else 0))

    returns = pnls
    if len(returns) > 1:
        avg_r = sum(returns) / len(returns)
        variance = sum((r - avg_r) ** 2 for r in returns) / len(returns)
        sharpe = (avg_r / math.sqrt(variance)) * math.sqrt(252) if variance > 0 else 0
    else:
        sharpe = 0

    max_dd = 0.0
    peak = equity_curve[0]
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    total_return = (balance - initial_balance) / initial_balance if initial_balance else 0

    return BacktestMetrics(
        total_trades=len(trades),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 2),
        expectancy=round(expectancy, 6),
        sharpe_ratio=round(sharpe, 2),
        max_drawdown=round(max_dd, 4),
        largest_win=round(max(wins), 6) if wins else 0,
        largest_loss=round(min(losses), 6) if losses else 0,
        total_return=round(total_return, 4),
        equity_curve=[round(v, 2) for v in equity_curve],
    )

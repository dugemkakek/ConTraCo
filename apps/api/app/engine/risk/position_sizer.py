"""Position sizing calculator — fixed fractional, Kelly, ATR-based."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionSize:
    size_units: float
    size_usd: float
    risk_pct: float
    stop_distance: float
    method: str
    reason: str = ""


def calculate_size(
    account_balance: float,
    entry_price: float,
    stop_price: float,
    risk_pct: float = 1.0,
    method: str = "fixed_fractional",
    win_rate: float | None = None,
    avg_win_loss_ratio: float | None = None,
    atr_value: float | None = None,
    atr_multiplier: float = 2.0,
) -> PositionSize:
    """Calculate position size using the selected method.

    fixed_fractional: size = (balance * risk_pct) / |entry - stop|
    kelly: f* = (win_rate * avg_win_loss_ratio - (1 - win_rate)) / avg_win_loss_ratio
    atr: stop_distance = atr * atr_multiplier, then fixed_fractional
    """
    stop_distance = abs(entry_price - stop_price)

    if method == "atr" and atr_value:
        stop_distance = max(stop_distance, atr_value * atr_multiplier)

    risk_amount = account_balance * (risk_pct / 100.0)

    if method == "kelly" and win_rate and avg_win_loss_ratio:
        kelly_f = (win_rate * avg_win_loss_ratio - (1 - win_rate)) / avg_win_loss_ratio
        kelly_f = max(0.0, min(kelly_f, 0.25))  # cap at 25%, never negative
        risk_amount = account_balance * kelly_f

    if stop_distance <= 0:
        return PositionSize(0, 0, risk_pct, 0, method, "stop_distance zero or negative")

    size_usd = risk_amount / stop_distance * entry_price if stop_distance > 0 else 0
    size_usd = min(size_usd, account_balance)  # can't risk more than balance
    size_units = size_usd / entry_price if entry_price > 0 else 0

    return PositionSize(
        size_units=round(size_units, 6),
        size_usd=round(size_usd, 2),
        risk_pct=risk_pct,
        stop_distance=round(stop_distance, 2),
        method=method,
    )

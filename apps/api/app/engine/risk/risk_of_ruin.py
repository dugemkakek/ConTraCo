"""Risk-of-ruin calculator + portfolio exposure tracker.

Risk of ruin (classic formula):
    RoR = ((1 - edge) / (1 + edge)) ^ (bankroll / unit_size)
    edge = win_rate - (1 - win_rate) / win_loss_ratio

Portfolio exposure: aggregate open-position notional vs account equity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class RiskOfRuinResult:
    risk_of_ruin_pct: float
    edge: float
    win_rate: float
    win_loss_ratio: float
    bankroll: float
    unit_size: float
    method: str = "classic"
    note: str = ""


def calculate_risk_of_ruin(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    bankroll: float,
    unit_size: float,
) -> RiskOfRuinResult:
    """Classic risk-of-ruin.

    Args:
        win_rate: fraction 0-1
        avg_win: average winning trade (positive)
        avg_loss: average losing trade (positive, absolute)
        bankroll: total account equity
        unit_size: risk per trade (dollar amount)
    """
    if avg_loss <= 0 or avg_win <= 0 or unit_size <= 0 or bankroll <= 0:
        return RiskOfRuinResult(100.0, 0, win_rate, 0, bankroll, unit_size,
                                note="invalid inputs — 100% ruin")

    win_loss_ratio = avg_win / avg_loss
    edge = win_rate - (1 - win_rate) / win_loss_ratio

    if edge <= 0:
        return RiskOfRuinResult(100.0, edge, win_rate, win_loss_ratio,
                                bankroll, unit_size,
                                note="no edge — ruin is certain")

    exponent = bankroll / unit_size
    base = (1 - edge) / (1 + edge)

    if base <= 0:
        ror = 0.0
    else:
        ror = base ** exponent

    return RiskOfRuinResult(
        risk_of_ruin_pct=round(min(ror * 100, 100.0), 4),
        edge=round(edge, 6),
        win_rate=win_rate,
        win_loss_ratio=round(win_loss_ratio, 4),
        bankroll=bankroll,
        unit_size=unit_size,
    )


@dataclass
class PositionExposure:
    symbol: str
    side: str
    notional: float
    pct_of_equity: float


@dataclass
class PortfolioExposureResult:
    total_notional: float
    total_pct: float
    equity: float
    positions: list[PositionExposure] = field(default_factory=list)
    long_pct: float = 0.0
    short_pct: float = 0.0
    net_pct: float = 0.0
    breached: bool = False
    cap_pct: float = 100.0


def calculate_portfolio_exposure(
    positions: list[dict],
    equity: float,
    cap_pct: float = 100.0,
) -> PortfolioExposureResult:
    """Aggregate open-position exposure.

    Each position dict: {"symbol", "side", "qty", "entry_price"} or
    {"symbol", "side", "notional"}.
    """
    if equity <= 0:
        return PortfolioExposureResult(0, 0, equity, cap_pct=cap_pct, breached=True)

    exposures: list[PositionExposure] = []
    total_long = 0.0
    total_short = 0.0

    for p in positions:
        notional = p.get("notional", 0.0)
        if not notional:
            notional = abs(p.get("qty", 0) * p.get("entry_price", 0))
        pct = (notional / equity) * 100
        side = p.get("side", "LONG").upper()
        exposures.append(PositionExposure(
            symbol=p.get("symbol", "?"), side=side,
            notional=round(notional, 2), pct_of_equity=round(pct, 2),
        ))
        if side == "LONG":
            total_long += notional
        else:
            total_short += notional

    total_notional = total_long + total_short
    total_pct = (total_notional / equity) * 100

    return PortfolioExposureResult(
        total_notional=round(total_notional, 2),
        total_pct=round(total_pct, 2),
        equity=round(equity, 2),
        positions=exposures,
        long_pct=round((total_long / equity) * 100, 2),
        short_pct=round((total_short / equity) * 100, 2),
        net_pct=round(((total_long - total_short) / equity) * 100, 2),
        breached=total_pct > cap_pct,
        cap_pct=cap_pct,
    )

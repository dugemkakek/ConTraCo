"""Trade plan generation, risk review, and synthesis summary.

All three are non-directional roles that run *after* the decision is
made. The runner calls them only when the final state is LONG_CANDIDATE
or SHORT_CANDIDATE — for WAIT/AVOID/DATA_INVALID there's no plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.db.models import Direction, FinalState
from app.engine.decision import DecisionResult
from app.indicators import atr


@dataclass
class PlanLevels:
    direction: Direction
    entry_price: float
    stop_price: float
    take_profit: float
    risk_reward: float
    position_size_pct: float  # % of equity to risk
    invalidation: str
    risk_review: str
    synthesis: str


def _round(x: float, n: int) -> float:
    if x == 0 or math.isnan(x):
        return x
    return round(x, n)


def build_plan(
    *,
    symbol: str,
    timeframe: str,
    candles: list,
    final_state: FinalState,
    decision: DecisionResult,
    spec_min_rr: float,
    spec_max_stop_atr: float,
) -> PlanLevels | None:
    """Build a trade plan, or return None if the decision is non-actionable."""
    if final_state not in (FinalState.LONG_CANDIDATE, FinalState.SHORT_CANDIDATE):
        return None
    if not candles:
        return None

    direction = Direction.LONG if final_state == FinalState.LONG_CANDIDATE else Direction.SHORT
    last = candles[-1]
    atr_series = atr(candles, 14)
    atr_v = atr_series[-1] if atr_series else max(last.close * 0.01, 0.01)
    if atr_v <= 0:
        atr_v = max(last.close * 0.01, 0.01)

    entry = last.close
    if direction == Direction.LONG:
        stop = entry - atr_v * 1.5
        take = entry + atr_v * 3.0  # ~2:1 by default; user can scale
    else:
        stop = entry + atr_v * 1.5
        take = entry - atr_v * 3.0

    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(take - entry)
    rr = reward_per_unit / risk_per_unit if risk_per_unit else 0.0

    # If RR doesn't meet the spec floor, push take-profit out (cap at
    # maximum_stop_atr_multiple so the stop isn't irrationally small).
    while rr < spec_min_rr and risk_per_unit > 0:
        new_reward = spec_min_rr * risk_per_unit
        new_take_offset = new_reward
        if direction == Direction.LONG:
            take = entry + new_take_offset
        else:
            take = entry - new_take_offset
        reward_per_unit = abs(take - entry)
        rr = reward_per_unit / risk_per_unit if risk_per_unit else 0.0
        if abs(take - entry) / atr_v > 6.0:
            break  # don't push further; the trade is what it is

    # Position sizing: 1% equity risk on a typical 1R setup, scaled by
    # composite score so stronger setups can use slightly more size.
    base_risk_pct = 1.0
    confidence_multiplier = min(abs(decision.composite_score) / 80.0, 1.0)
    position_size_pct = _round(base_risk_pct * (0.5 + 0.5 * confidence_multiplier), 2)

    invalidation = (
        f"Close {'below' if direction == Direction.LONG else 'above'} "
        f"{_round(stop, 4)} on the {timeframe} timeframe"
    )
    risk_review = (
        f"Stop is {abs(entry - stop) / atr_v:.1f}×ATR "
        f"(max {spec_max_stop_atr:.1f}×). R/R is {rr:.2f} "
        f"(min {spec_min_rr:.2f}). Position size: {position_size_pct}% of equity."
    )
    synthesis = (
        f"{direction.value} candidate on {symbol} {timeframe}. "
        f"Composite {decision.composite_score:+.1f}, "
        f"gate score {decision.gate_score:+.1f}, "
        f"model score {decision.model_score:+.1f}, "
        f"agreement {decision.model_agreement:.0%}."
    )

    return PlanLevels(
        direction=direction,
        entry_price=_round(entry, 6),
        stop_price=_round(stop, 6),
        take_profit=_round(take, 6),
        risk_reward=_round(rr, 3),
        position_size_pct=position_size_pct,
        invalidation=invalidation,
        risk_review=risk_review,
        synthesis=synthesis,
    )


__all__ = ["PlanLevels", "build_plan"]

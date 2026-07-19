"""Fibonacci retracement and extension levels gate."""

from __future__ import annotations

import logging

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation

logger = logging.getLogger(__name__)

FIB_RETRACEMENT = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_EXTENSION = [1.272, 1.618, 2.0, 2.618]


class FibonacciLevelsGate:
    name = "fibonacci_levels"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name, status=GateStatus.UNAVAILABLE, score=0.0,
                confidence=0.0, reason="insufficient candles (need >=30)",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        last_close = closes[-1]

        # Recent swing high/low
        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])
        swing_range = recent_high - recent_low

        if swing_range <= 0:
            return GateEvaluation(
                name=self.name, status=GateStatus.UNAVAILABLE, score=0.0,
                confidence=0.0, reason="no valid swing range",
            )

        # Calculate retracement levels
        levels: dict[str, float] = {}
        for fib in FIB_RETRACEMENT:
            levels[f"ret_{fib:.3f}"] = round(recent_high - swing_range * fib, 2)
        for fib in FIB_EXTENSION:
            levels[f"ext_{fib:.3f}"] = round(recent_high + swing_range * (fib - 1), 2)

        # Score by proximity to key levels
        closest_fib, min_dist = "", float("inf")
        for name, level in levels.items():
            dist = abs(last_close - level) / swing_range
            if dist < min_dist:
                min_dist = dist
                closest_fib = name

        score = 0.65 if min_dist < 0.05 else (0.45 if min_dist < 0.1 else 0.0)
        return GateEvaluation(
            name=self.name, status=GateStatus.PASS, score=score, confidence=1.0,
            reason=f"Price {min_dist:.1%} from {closest_fib}",
            evidence=levels,
        )

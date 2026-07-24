"""Fibonacci retracement and extension levels gate.

Fix: original only returned scores 0.0, 0.45, 0.65 — never negative,
never FAIL. Gate was permanently bullish or neutral, corrupting the
confluence sum.

Now:
- Determines the dominant swing direction (up or down) over last 20 bars
- Near a retracement level AFTER an upswing → support → positive score
- Near a retracement level AFTER a downswing → resistance → negative score
- Near an extension level in trend direction → continuation signal
- Distance to level scales the score (closer = stronger)
"""

from __future__ import annotations

import logging

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation

logger = logging.getLogger(__name__)

FIB_RETRACEMENT = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_EXTENSION = [1.272, 1.618, 2.0, 2.618]

# Score magnitude by proximity bucket
_PROX_SCORE = [
    (0.02, 80.0),   # within 2% of swing range → strong
    (0.05, 60.0),   # within 5%
    (0.10, 40.0),   # within 10%
    (0.15, 20.0),   # within 15%
]


def _proximity_score(dist_ratio: float) -> float:
    """Map normalised distance to a magnitude 0..80."""
    for threshold, score in _PROX_SCORE:
        if dist_ratio <= threshold:
            return score
    return 0.0


class FibonacciLevelsGate:
    name = "fibonacci_levels"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient candles (need >=30)",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        last_close = closes[-1]

        # Swing range over last 20 bars
        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])
        swing_range = recent_high - recent_low

        if swing_range <= 0:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="no valid swing range",
            )

        # Determine dominant swing direction over last 20 bars
        # If the swing high came AFTER the swing low → upswing (bullish context)
        # If the swing low came AFTER the swing high → downswing (bearish context)
        high_idx = highs[-20:].index(recent_high)
        low_idx = lows[-20:].index(recent_low)
        upswing = high_idx > low_idx  # high formed more recently than low

        # Retracement levels (measured from the swing in the dominant direction)
        ret_levels: dict[str, float] = {}
        if upswing:
            # Retracement pulls DOWN from recent_high toward recent_low
            for fib in FIB_RETRACEMENT:
                ret_levels[f"ret_{fib:.3f}"] = recent_high - swing_range * fib
        else:
            # Retracement bounces UP from recent_low toward recent_high
            for fib in FIB_RETRACEMENT:
                ret_levels[f"ret_{fib:.3f}"] = recent_low + swing_range * fib

        # Extension levels (continuation beyond the swing)
        ext_levels: dict[str, float] = {}
        if upswing:
            for fib in FIB_EXTENSION:
                ext_levels[f"ext_{fib:.3f}"] = recent_low + swing_range * fib
        else:
            for fib in FIB_EXTENSION:
                ext_levels[f"ext_{fib:.3f}"] = recent_high - swing_range * (fib - 1)

        all_levels = {**ret_levels, **ext_levels}

        # Find the closest level
        closest_name, min_dist_ratio = "", float("inf")
        for lvl_name, level in all_levels.items():
            dist_ratio = abs(last_close - level) / swing_range
            if dist_ratio < min_dist_ratio:
                min_dist_ratio = dist_ratio
                closest_name = lvl_name

        mag = _proximity_score(min_dist_ratio)

        if mag == 0.0:
            # Price is not near any significant Fib level
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.2,
                reason=f"price not near any Fib level (closest: {closest_name} at {min_dist_ratio:.1%})",
                evidence={**all_levels, "closest": closest_name, "dist_ratio": round(min_dist_ratio, 4)},
            )

        is_retracement = closest_name.startswith("ret_")

        # Directional logic:
        # Upswing + price at retracement = support = BULLISH
        # Upswing + price at extension   = resistance / profit target = mildly BEARISH
        # Downswing + price at retracement = resistance = BEARISH
        # Downswing + price at extension  = support / bounce target = mildly BULLISH
        if upswing and is_retracement:
            score = mag          # bullish: price pulling back to support
            direction_note = "retracement support in upswing"
        elif upswing and not is_retracement:
            score = -mag * 0.5   # mildly bearish: hitting extension resistance
            direction_note = "extension resistance in upswing"
        elif not upswing and is_retracement:
            score = -mag         # bearish: bouncing up into resistance
            direction_note = "retracement resistance in downswing"
        else:  # downswing + extension
            score = mag * 0.5    # mildly bullish: reaching extension support
            direction_note = "extension support in downswing"

        score = max(-100.0, min(100.0, score))
        confidence = min(0.4 + mag / 100.0 * 0.5, 0.9)

        if score > 15:
            status = GateStatus.PASS
        elif score < -15:
            status = GateStatus.FAIL
        else:
            status = GateStatus.NEUTRAL

        fib_val = all_levels[closest_name]
        reason = (
            f"{direction_note}: price {last_close:.4f} is {min_dist_ratio:.1%} "
            f"from {closest_name} ({fib_val:.4f})"
        )

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "retracement_levels": {k: round(v, 6) for k, v in ret_levels.items()},
                "extension_levels": {k: round(v, 6) for k, v in ext_levels.items()},
                "closest_level": closest_name,
                "closest_price": round(all_levels[closest_name], 6),
                "dist_ratio": round(min_dist_ratio, 4),
                "upswing": upswing,
                "swing_high": round(recent_high, 6),
                "swing_low": round(recent_low, 6),
                "swing_range": round(swing_range, 6),
            },
        )

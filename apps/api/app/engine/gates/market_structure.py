"""Market structure gate: swing highs/lows and break-of-structure."""

from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation
from app.indicators import swing_highs_lows


class MarketStructureGate:
    name = "market_structure"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for structure analysis (need >=30 bars)",
            )

        highs, lows = swing_highs_lows(candles, lookback=3)
        last_close = candles[-1].close
        if not highs or not lows:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.3,
                reason="no clear swing structure; range unclear",
                evidence={"swing_highs": 0, "swing_lows": 0},
            )

        # BOS = close above the highest swing high -> bullish structure
        # CHoCH = close below the most recent swing low after a bullish run
        sorted_highs = sorted(highs.items())  # by index
        sorted_lows = sorted(lows.items())

        # Most recent swing high/low seen *before* the current bar.
        prior_highs = [(i, p) for i, p in sorted_highs if i < len(candles) - 1]
        prior_lows = [(i, p) for i, p in sorted_lows if i < len(candles) - 1]
        if not prior_highs or not prior_lows:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.3,
                reason="no prior swings; structure forming",
            )
        last_swing_high = prior_highs[-1][1]
        last_swing_low = prior_lows[-1][1]

        bos_up = last_close > last_swing_high
        bos_down = last_close < last_swing_low
        range_position = (last_close - last_swing_low) / max(
            last_swing_high - last_swing_low, 1e-9
        )

        if bos_up:
            score = 60.0
            status = GateStatus.PASS
            reason = f"break-of-structure up: close {last_close:.2f} > swing high {last_swing_high:.2f}"
        elif bos_down:
            score = -60.0
            status = GateStatus.FAIL
            reason = f"break-of-structure down: close {last_close:.2f} < swing low {last_swing_low:.2f}"
        else:
            # Inside the range: lean toward whichever side has the most swing points recently
            if range_position > 0.6:
                score = 30.0
                status = GateStatus.PASS
                reason = f"upper range ({range_position:.0%}); bullish lean"
            elif range_position < 0.4:
                score = -30.0
                status = GateStatus.FAIL
                reason = f"lower range ({range_position:.0%}); bearish lean"
            else:
                score = 0.0
                status = GateStatus.NEUTRAL
                reason = f"mid-range ({range_position:.0%})"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=0.7,
            reason=reason,
            evidence={
                "swing_highs": len(highs),
                "swing_lows": len(lows),
                "last_swing_high": round(last_swing_high, 6),
                "last_swing_low": round(last_swing_low, 6),
                "range_position": round(range_position, 4),
                "bos_up": bos_up,
                "bos_down": bos_down,
            },
        )

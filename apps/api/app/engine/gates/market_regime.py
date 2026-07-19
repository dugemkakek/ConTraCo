"""Market regime gate.

Identifies whether the market is in a trending or ranging state and
which direction the trend has, by combining EMA slopes and ADX.
"""

from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation
from app.indicators import adx, ema


class MarketRegimeGate:
    name = "market_regime"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 60:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for regime detection (need >=60 bars)",
            )

        closes = [c.close for c in candles]
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema200 = ema(closes, 200) if len(closes) >= 200 else ema(closes, len(closes))
        adx_series = adx(candles, 14)

        last = -1
        slope20 = (ema20[last] - ema20[last - 20]) / max(ema20[last - 20], 1e-9)
        slope50 = (ema50[last] - ema50[last - 20]) / max(ema50[last - 20], 1e-9)
        adx_last = adx_series[last]
        bullish_stack = ema20[last] > ema50[last] > ema200[last]
        bearish_stack = ema20[last] < ema50[last] < ema200[last]

        # score: -100..100, based on trend direction + ADX strength
        direction = 0.0
        if bullish_stack:
            direction = 1.0
        elif bearish_stack:
            direction = -1.0
        else:
            direction = max(min(slope20 * 50, 1.0), -1.0)

        strength = max(0.0, min(1.0, adx_last / 50.0))
        score = direction * strength * 100.0

        if adx_last < 18:
            status = GateStatus.NEUTRAL
            reason = f"ranging (ADX={adx_last:.1f}); no directional bias"
        elif score > 15:
            status = GateStatus.PASS
            reason = f"uptrend (ADX={adx_last:.1f}, ema20/50/200 stacked bullish)"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"downtrend (ADX={adx_last:.1f}, ema20/50/200 stacked bearish)"
        else:
            status = GateStatus.NEUTRAL
            reason = f"weak trend (ADX={adx_last:.1f}); no clear bias"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=strength,
            reason=reason,
            evidence={
                "adx": round(adx_last, 2),
                "ema20": round(ema20[last], 6),
                "ema50": round(ema50[last], 6),
                "ema200": round(ema200[last], 6),
                "ema20_slope_per_20bars": round(slope20, 4),
                "ema50_slope_per_20bars": round(slope50, 4),
                "bullish_stack": bullish_stack,
                "bearish_stack": bearish_stack,
            },
        )

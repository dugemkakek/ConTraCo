"""Smart Money Concepts gate — BOS, CHoCH, FVG, Order Blocks."""

from __future__ import annotations

import logging

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation

logger = logging.getLogger(__name__)


class SMCStructureGate:
    name = "smc_structure"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 20:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient candles (need >=20)",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        score = 0.0
        details: list[str] = []

        # Swing highs/lows (lookback=5)
        swing_highs: list[int] = []
        swing_lows: list[int] = []
        for i in range(5, len(candles) - 5):
            if all(highs[i] >= highs[j] for j in range(i - 5, i + 6) if j != i):
                swing_highs.append(i)
            if all(lows[i] <= lows[j] for j in range(i - 5, i + 6) if j != i):
                swing_lows.append(i)

        # Break of Structure — bullish: higher swing high
        if len(swing_highs) >= 2 and highs[swing_highs[-1]] > highs[swing_highs[-2]]:
            score += 30.0
            details.append("BOS upside (higher swing high)")

        # Break of Structure — bearish: lower swing low
        if len(swing_lows) >= 2 and lows[swing_lows[-1]] < lows[swing_lows[-2]]:
            score -= 30.0
            details.append("BOS downside (lower swing low)")

        # Change of Character — bullish BOS followed by close below prior swing low
        if swing_lows and closes[-1] < lows[swing_lows[-1]]:
            score -= 20.0
            details.append("CHoCH: close below prior swing low")
        elif swing_highs and closes[-1] > highs[swing_highs[-1]]:
            score += 20.0
            details.append("CHoCH: close above prior swing high")

        # Fair Value Gaps
        fvg_score = 0.0
        for i in range(2, len(candles)):
            if lows[i] > highs[i - 2]:  # bullish FVG
                fvg_score += 15.0
                details.append(f"bullish FVG at bar {i}")
                break
        for i in range(2, len(candles)):
            if highs[i] < lows[i - 2]:  # bearish FVG
                fvg_score -= 15.0
                details.append(f"bearish FVG at bar {i}")
                break
        score += fvg_score

        # Order Blocks: last bearish candle before a bullish BOS = bullish OB
        ob_score = 0.0
        if len(swing_highs) >= 2 and highs[swing_highs[-1]] > highs[swing_highs[-2]]:
            # Look for the last red candle before the swing high
            for i in range(swing_highs[-1], max(0, swing_highs[-1] - 5), -1):
                if closes[i] < candles[i].open:
                    ob_score += 10.0
                    details.append(f"bullish order block at bar {i}")
                    break
        score += ob_score

        score = max(-100.0, min(100.0, score))

        # Confidence: based on how many signals fired
        n_signals = len(details)
        confidence = min(0.3 + n_signals * 0.15, 0.9)

        if score > 15:
            status = GateStatus.PASS
        elif score < -15:
            status = GateStatus.FAIL
        else:
            status = GateStatus.NEUTRAL

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason="; ".join(details) if details else "no significant SMC patterns",
            evidence={
                "swing_highs": len(swing_highs),
                "swing_lows": len(swing_lows),
                "fvg_score": fvg_score,
                "ob_score": ob_score,
                "patterns": details,
            },
        )

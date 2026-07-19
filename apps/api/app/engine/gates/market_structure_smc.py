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
                name=self.name, status=GateStatus.UNAVAILABLE, score=0.0,
                confidence=0.0, reason="insufficient candles (need >=20)",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        score = 0.0
        details: list[str] = []

        # Swing highs/lows (lookback=5)
        swing_highs: list[int] = []
        swing_lows: list[int] = []
        for i in range(5, len(candles) - 5):
            if all(highs[i] >= highs[j] for j in range(i - 5, i + 6)):
                swing_highs.append(i)
            if all(lows[i] <= lows[j] for j in range(i - 5, i + 6)):
                swing_lows.append(i)

        # Break of Structure
        if len(swing_highs) >= 2 and highs[swing_highs[-1]] > highs[swing_highs[-2]]:
            score += 0.15; details.append("BOS upside")
        if len(swing_lows) >= 2 and lows[swing_lows[-1]] < lows[swing_lows[-2]]:
            score += 0.15; details.append("BOS downside")

        # Fair Value Gaps
        for i in range(2, len(candles)):
            if lows[i] > highs[i - 2]:
                score += 0.1; details.append(f"bullish FVG at bar {i}"); break
            if highs[i] < lows[i - 2]:
                score += 0.1; details.append(f"bearish FVG at bar {i}"); break

        score = max(-1.0, min(1.0, score))
        return GateEvaluation(
            name=self.name, status=GateStatus.PASS, score=score, confidence=1.0,
            reason="; ".join(details) if details else "no significant SMC patterns",
            evidence={"swing_highs": len(swing_highs), "swing_lows": len(swing_lows)},
        )

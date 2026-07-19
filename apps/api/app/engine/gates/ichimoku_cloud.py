"""Ichimoku Cloud gate — Tenkan, Kijun, Senkou, Chikou."""

from __future__ import annotations

import logging

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation

logger = logging.getLogger(__name__)


class IchimokuCloudGate:
    name = "ichimoku_cloud"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 60:
            return GateEvaluation(
                name=self.name, status=GateStatus.UNAVAILABLE, score=0.0,
                confidence=0.0, reason="need 60+ candles for Ichimoku",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        def hhv(p: int, off: int = 0) -> float: return max(highs[-(off + p):len(highs) - off] if off else highs[-p:]) if len(highs) >= off + p else highs[-1]
        def llv(p: int, off: int = 0) -> float: return min(lows[-(off + p):len(lows) - off] if off else lows[-p:]) if len(lows) >= off + p else lows[-1]

        tenkan = (hhv(9) + llv(9)) / 2.0
        kijun = (hhv(26) + llv(26)) / 2.0
        senkou_a = (tenkan + kijun) / 2.0
        senkou_b = (hhv(52) + llv(52)) / 2.0
        chikou = closes[-26] if len(closes) >= 26 else closes[0]
        last_close = closes[-1]
        cloud_top = max(senkou_a, senkou_b)
        cloud_bot = min(senkou_a, senkou_b)

        bullish = 0
        if last_close > cloud_top: bullish += 1
        if tenkan > kijun: bullish += 1
        if chikou > closes[-52] if len(closes) >= 52 else closes[0]: bullish += 1
        if senkou_a > senkou_b: bullish += 1

        score = bullish / 4.0
        return GateEvaluation(
            name=self.name, status=GateStatus.PASS, score=score, confidence=1.0,
            reason=f"Ichimoku: {bullish}/4 bullish conditions",
            evidence={"tenkan": round(tenkan, 2), "kijun": round(kijun, 2),
                      "senkou_a": round(senkou_a, 2), "senkou_b": round(senkou_b, 2)},
        )

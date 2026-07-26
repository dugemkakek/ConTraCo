"""Ichimoku Cloud gate — Tenkan, Kijun, Senkou, Chikou.

Fix: score was 0..1 (bullish_count/4) — never negative, never bearish.
Now returns full -100..100 range: (bullish - bearish) / 4 * 100.
Status and confidence are computed dynamically, not hardcoded.
"""

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
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="need 60+ candles for Ichimoku",
            )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        def hhv(p: int, off: int = 0) -> float:
            src = highs[-(off + p): len(highs) - off] if off else highs[-p:]
            return max(src) if src else highs[-1]

        def llv(p: int, off: int = 0) -> float:
            src = lows[-(off + p): len(lows) - off] if off else lows[-p:]
            return min(src) if src else lows[-1]

        tenkan = (hhv(9) + llv(9)) / 2.0
        kijun = (hhv(26) + llv(26)) / 2.0
        senkou_a = (tenkan + kijun) / 2.0
        senkou_b = (hhv(52) + llv(52)) / 2.0
        chikou_ref = closes[-52] if len(closes) >= 52 else closes[0]
        chikou_val = closes[-26] if len(closes) >= 26 else closes[0]
        last_close = closes[-1]
        cloud_top = max(senkou_a, senkou_b)
        cloud_bot = min(senkou_a, senkou_b)

        # Each condition contributes +1 (bullish) or -1 (bearish)
        conditions: list[tuple[str, int]] = [
            ("price_above_cloud", 1 if last_close > cloud_top else -1 if last_close < cloud_bot else 0),
            ("tenkan_above_kijun", 1 if tenkan > kijun else -1),
            ("chikou_above_past", 1 if chikou_val > chikou_ref else -1),
            ("senkou_a_above_b", 1 if senkou_a > senkou_b else -1),
        ]

        bullish = sum(1 for _, v in conditions if v > 0)
        bearish = sum(1 for _, v in conditions if v < 0)
        neutral = sum(1 for _, v in conditions if v == 0)

        # Score: net directional signal scaled to -100..100
        score = (bullish - bearish) / 4.0 * 100.0

        # Confidence: how strongly the conditions agree
        # 4/4 agreement → 1.0, 3/4 → 0.75, 2/4 → 0.5, split → 0.3
        max_side = max(bullish, bearish)
        confidence = max_side / 4.0 if max_side > 0 else 0.3

        if score > 15:
            status = GateStatus.PASS
            reason = (
                f"Ichimoku bullish: {bullish}/4 conditions met "
                f"(price={'above' if last_close > cloud_top else 'in' if last_close >= cloud_bot else 'below'} cloud, "
                f"T/K={'above' if tenkan > kijun else 'below'})"
            )
        elif score < -15:
            status = GateStatus.FAIL
            reason = (
                f"Ichimoku bearish: {bearish}/4 conditions against "
                f"(price={'below' if last_close < cloud_bot else 'in'} cloud, "
                f"T/K={'below' if tenkan < kijun else 'above'})"
            )
        else:
            status = GateStatus.NEUTRAL
            reason = f"Ichimoku mixed: {bullish} bull / {bearish} bear / {neutral} neutral conditions"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "tenkan": round(tenkan, 6),
                "kijun": round(kijun, 6),
                "senkou_a": round(senkou_a, 6),
                "senkou_b": round(senkou_b, 6),
                "cloud_top": round(cloud_top, 6),
                "cloud_bot": round(cloud_bot, 6),
                "chikou": round(chikou_val, 6),
                "last_close": round(last_close, 6),
                "bullish_conditions": bullish,
                "bearish_conditions": bearish,
                "conditions": {name: v for name, v in conditions},
            },
        )

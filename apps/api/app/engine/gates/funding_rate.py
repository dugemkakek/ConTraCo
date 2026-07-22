"""Funding Rate gate (spec 03, gate 5).

Derivatives positioning read: cross-exchange funding, predicted funding,
OI trend, long/short ratio.

Deterministic computation first; LLM only narrates (spec 03 contract).
"""
from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class FundingRateGate:
    name = "funding_rate"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        meta = ctx.symbol_meta or {}
        funding_rate = meta.get("funding_rate")
        predicted_funding = meta.get("predicted_funding")
        oi_change_pct = meta.get("oi_change_pct")
        long_short_ratio = meta.get("long_short_ratio")

        # Need at least funding_rate to produce a verdict
        if funding_rate is None:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient data: no funding rate available",
            )

        signals: list[tuple[str, float]] = []

        # Funding rate signal:
        # Positive funding → longs pay shorts → crowded long → bearish bias
        # Negative funding → shorts pay longs → crowded short → bullish bias
        if funding_rate > 0.05:
            signals.append(("funding_crowded_long", -1.0))
        elif funding_rate < -0.05:
            signals.append(("funding_crowded_short", 1.0))
        elif funding_rate > 0.01:
            signals.append(("funding_mild_long", -0.4))
        elif funding_rate < -0.01:
            signals.append(("funding_mild_short", 0.4))
        else:
            signals.append(("funding_neutral", 0.0))

        # Predicted funding divergence (if available)
        if predicted_funding is not None:
            divergence = predicted_funding - funding_rate
            if divergence > 0.02:
                signals.append(("predicted_funding_rising", -0.5))
            elif divergence < -0.02:
                signals.append(("predicted_funding_falling", 0.5))
            else:
                signals.append(("predicted_funding_stable", 0.0))

        # OI trend: rising OI + rising price = strong trend confirmation
        # Rising OI + falling price = aggressive shorting
        if oi_change_pct is not None:
            if oi_change_pct > 5:
                signals.append(("oi_surging", -0.3))  # overleveraged
            elif oi_change_pct < -5:
                signals.append(("oi_collapsing", 0.3))  # deleveraging = relief
            else:
                signals.append(("oi_stable", 0.0))

        # Long/short ratio: >2 = crowded long, <0.5 = crowded short
        if long_short_ratio is not None:
            if long_short_ratio > 2.0:
                signals.append(("ls_crowded_long", -0.6))
            elif long_short_ratio < 0.5:
                signals.append(("ls_crowded_short", 0.6))
            else:
                signals.append(("ls_balanced", 0.0))

        score = sum(s for _, s in signals) / len(signals) * 100.0
        signs = [1 if s > 0 else -1 if s < 0 else 0 for _, s in signals]
        pos = sum(1 for x in signs if x > 0)
        neg = sum(1 for x in signs if x < 0)
        confidence = max(pos, neg) / len(signals) if signs else 0.0

        if score > 15:
            status = GateStatus.PASS
            reason = f"funding/positioning bullish (rate={funding_rate:.4f})"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"funding/positioning bearish (rate={funding_rate:.4f})"
        else:
            status = GateStatus.NEUTRAL
            reason = f"funding/positioning neutral (rate={funding_rate:.4f})"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "funding_rate": funding_rate,
                "predicted_funding": predicted_funding,
                "oi_change_pct": oi_change_pct,
                "long_short_ratio": long_short_ratio,
                "sub_signals": {k: round(v, 4) for k, v in signals},
            },
        )

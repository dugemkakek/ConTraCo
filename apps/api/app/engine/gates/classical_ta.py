"""Classical TA gate: RSI, MACD, Bollinger %b, stochastic-RSI style.

Produces a single score in -100..100 with confidence 0..1 representing
how many sub-signals agree.
"""

from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation
from app.indicators import bollinger, macd, rsi


class ClassicalTAGate:
    name = "classical_ta"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for classical indicators (need >=30 bars)",
            )

        closes = [c.close for c in candles]
        rsi_series = rsi(closes, 14)
        macd_line, signal_line, hist = macd(closes)
        _, _, _, pb = bollinger(closes)

        rsi_v = rsi_series[-1]
        macd_v = macd_line[-1]
        sig_v = signal_line[-1]
        hist_v = hist[-1]
        pb_v = pb[-1]

        sub_scores: list[tuple[str, float]] = []
        # RSI: <30 bullish mean-reversion (+1), >70 bearish mean-reversion (-1)
        if rsi_v < 30:
            sub_scores.append(("rsi_oversold", 1.0))
        elif rsi_v > 70:
            sub_scores.append(("rsi_overbought", -1.0))
        else:
            sub_scores.append(("rsi_neutral", (50 - rsi_v) / 50.0))
        # MACD histogram sign
        sub_scores.append(("macd_hist", 1.0 if hist_v > 0 else -1.0))
        # Bollinger %b: <0.2 mean-revert long, >0.8 mean-revert short, else trend
        if pb_v < 0.2:
            sub_scores.append(("bb_lower", 1.0))
        elif pb_v > 0.8:
            sub_scores.append(("bb_upper", -1.0))
        else:
            sub_scores.append(("bb_neutral", (0.5 - pb_v) * 2.0))

        score = sum(s for _, s in sub_scores) / len(sub_scores) * 100.0
        # Confidence: how many sub-signals agree on sign.
        signs = [1 if s > 0 else -1 if s < 0 else 0 for _, s in sub_scores]
        pos = sum(1 for x in signs if x > 0)
        neg = sum(1 for x in signs if x < 0)
        agreement = max(pos, neg) / len(signs)
        confidence = agreement

        if score > 20:
            status = GateStatus.PASS
            reason = f"classical TA bullish (RSI={rsi_v:.1f}, MACD hist={hist_v:.2f}, %b={pb_v:.2f})"
        elif score < -20:
            status = GateStatus.FAIL
            reason = f"classical TA bearish (RSI={rsi_v:.1f}, MACD hist={hist_v:.2f}, %b={pb_v:.2f})"
        else:
            status = GateStatus.NEUTRAL
            reason = f"classical TA mixed (RSI={rsi_v:.1f}, MACD hist={hist_v:.2f}, %b={pb_v:.2f})"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "rsi14": round(rsi_v, 2),
                "macd": round(macd_v, 4),
                "macd_signal": round(sig_v, 4),
                "macd_hist": round(hist_v, 4),
                "bollinger_pct_b": round(pb_v, 4),
                "sub_signals": {k: round(v, 4) for k, v in sub_scores},
            },
        )

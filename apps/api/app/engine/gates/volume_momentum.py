"""Volume/momentum gate: volume vs moving average, OBV slope, delta."""

from __future__ import annotations

from app.indicators import obv, sma


from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class VolumeMomentumGate:
    name = "volume_momentum"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for volume analysis (need >=30 bars)",
            )

        volumes = [c.volume for c in candles]
        closes = [c.close for c in candles]

        vol_avg = sma(volumes, 20)[-1]
        vol_recent = sum(volumes[-5:]) / 5.0
        vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1.0

        # OBV slope over last 20 bars
        obv_series = obv(candles)
        if len(obv_series) >= 21:
            slope = (obv_series[-1] - obv_series[-21]) / max(abs(obv_series[-21]), 1.0)
        else:
            slope = 0.0

        # Price momentum over last 10 bars
        if len(closes) >= 11:
            momentum = (closes[-1] - closes[-11]) / closes[-11]
        else:
            momentum = 0.0

        # Score combines: high volume + positive OBV + positive momentum
        vol_signal = max(min((vol_ratio - 1.0) * 2.0, 1.0), -1.0)  # -1..1
        obv_signal = max(min(slope * 5.0, 1.0), -1.0)
        mom_signal = max(min(momentum * 10.0, 1.0), -1.0)

        score = ((vol_signal + obv_signal + mom_signal) / 3.0) * 100.0

        if score > 15:
            status = GateStatus.PASS
            reason = (
                f"volume confirms momentum: vol x{vol_ratio:.2f} avg, "
                f"OBV slope {slope:+.2%}, price mom {momentum:+.2%}"
            )
        elif score < -15:
            status = GateStatus.FAIL
            reason = (
                f"volume/momentum bearish: vol x{vol_ratio:.2f} avg, "
                f"OBV slope {slope:+.2%}, price mom {momentum:+.2%}"
            )
        else:
            status = GateStatus.NEUTRAL
            reason = (
                f"volume/momentum mixed: vol x{vol_ratio:.2f} avg, "
                f"OBV slope {slope:+.2%}, price mom {momentum:+.2%}"
            )

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=0.6,
            reason=reason,
            evidence={
                "vol_ratio_5vs20": round(vol_ratio, 4),
                "obv_slope_per_20": round(slope, 4),
                "price_momentum_10": round(momentum, 4),
                "sub_signals": {
                    "vol": round(vol_signal, 4),
                    "obv": round(obv_signal, 4),
                    "momentum": round(mom_signal, 4),
                },
            },
        )

"""Liquidity Heatmap gate (spec 03, gate 6).

Liquidation cluster estimation, liquidity voids.
Uses estimated liquidation levels from leverage + entry price distribution.
Deterministic only.
"""
from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class LiquidityHeatmapGate:
    name = "liquidity_heatmap"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        meta = ctx.symbol_meta or {}

        if len(candles) < 50:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for liquidity estimation (need >=50 bars)",
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        current = closes[-1]

        signals: list[tuple[str, float]] = []

        # 1. Swing high/low clusters = liquidity magnets
        # Find recent swing highs (resistance) and swing lows (support)
        swing_highs: list[float] = []
        swing_lows: list[float] = []
        lookback = min(5, len(candles) // 4)
        for i in range(lookback, len(candles) - lookback):
            if highs[i] == max(highs[i - lookback:i + lookback + 1]):
                swing_highs.append(highs[i])
            if lows[i] == min(lows[i - lookback:i + lookback + 1]):
                swing_lows.append(lows[i])

        # Nearest swing high above price = short liquidation cluster
        above = [h for h in swing_highs if h > current]
        below = [l for l in swing_lows if l < current]

        nearest_resistance = min(above) if above else None
        nearest_support = max(below) if below else None

        # 2. Distance to liquidity clusters
        if nearest_resistance and nearest_support:
            dist_to_res = (nearest_resistance - current) / current * 100
            dist_to_sup = (current - nearest_support) / current * 100

            # Price closer to support = bullish magnet below
            if dist_to_sup < dist_to_res * 0.5:
                signals.append(("near_support_magnet", 0.7))
            elif dist_to_res < dist_to_sup * 0.5:
                signals.append(("near_resistance_magnet", -0.7))
            else:
                signals.append(("equidistant_liquidity", 0.0))

            evidence_dist = {
                "nearest_resistance": round(nearest_resistance, 6),
                "nearest_support": round(nearest_support, 6),
                "dist_to_resistance_pct": round(dist_to_res, 3),
                "dist_to_support_pct": round(dist_to_sup, 3),
            }
        else:
            signals.append(("no_clear_clusters", 0.0))
            evidence_dist = {}

        # 3. Liquidity void detection: large candles with low volume = gap
        # that price tends to fill
        volumes = [c.volume for c in candles]
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / max(len(volumes), 1)
        recent_range = max(highs[-5:]) - min(lows[-5:])
        avg_range = sum(h - l for h, l in zip(highs[-20:], lows[-20:])) / 20 if len(highs) >= 20 else recent_range

        if avg_vol > 0 and recent_range > avg_range * 2:
            # Large move on relatively normal volume = potential void
            signals.append(("liquidity_void_detected", -0.3))
        else:
            signals.append(("no_liquidity_void", 0.0))

        # 4. External liquidation data (if available from meta)
        liq_clusters = meta.get("liquidation_clusters")
        if liq_clusters and isinstance(liq_clusters, list):
            long_liq = sum(c.get("size", 0) for c in liq_clusters if c.get("side") == "long")
            short_liq = sum(c.get("size", 0) for c in liq_clusters if c.get("side") == "short")
            total_liq = long_liq + short_liq
            if total_liq > 0:
                short_ratio = short_liq / total_liq
                if short_ratio > 0.65:
                    signals.append(("short_liq_dominant", 0.5))  # squeeze potential
                elif short_ratio < 0.35:
                    signals.append(("long_liq_dominant", -0.5))  # cascade risk
                else:
                    signals.append(("balanced_liq", 0.0))

        score = sum(s for _, s in signals) / max(len(signals), 1) * 100.0
        signs = [1 if s > 0 else -1 if s < 0 else 0 for _, s in signals]
        pos = sum(1 for x in signs if x > 0)
        neg = sum(1 for x in signs if x < 0)
        confidence = max(pos, neg) / len(signals) if signs else 0.0

        if score > 15:
            status = GateStatus.PASS
            reason = "liquidity map bullish (support magnets dominant)"
        elif score < -15:
            status = GateStatus.FAIL
            reason = "liquidity map bearish (resistance magnets dominant)"
        else:
            status = GateStatus.NEUTRAL
            reason = "liquidity map neutral (no dominant magnet)"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "swing_highs": len(swing_highs),
                "swing_lows": len(swing_lows),
                **evidence_dist,
                "sub_signals": {k: round(v, 4) for k, v in signals},
            },
        )

"""Pattern Recognition gate (spec 03, gate 7).

Algorithmic chart pattern detection: head & shoulders, flags,
double tops/bottoms, triangles. Deterministic detection; LLM narrates.
"""
from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class PatternRecognitionGate:
    name = "pattern_recognition"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        candles = ctx.candles
        if len(candles) < 30:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient history for pattern detection (need >=30 bars)",
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        n = len(closes)

        patterns: list[tuple[str, float]] = []  # (name, direction_score)

        # --- Double Top / Bottom ---
        # Look for two peaks/troughs at similar levels
        window = min(20, n // 2)
        recent_highs = highs[-window:]
        recent_lows = lows[-window:]
        mid = n - window // 2

        # Double top: two peaks within 1% of each other, separated by a dip
        peak_indices = [i for i in range(1, len(recent_highs) - 1)
                        if recent_highs[i] > recent_highs[i-1] and recent_highs[i] > recent_highs[i+1]]
        if len(peak_indices) >= 2:
            p1, p2 = peak_indices[-2], peak_indices[-1]
            if abs(recent_highs[p1] - recent_highs[p2]) / recent_highs[p1] < 0.01:
                # Check for valley between them
                valley = min(recent_lows[p1:p2+1]) if p2 > p1 else 0
                if valley < recent_highs[p1] * 0.98:
                    patterns.append(("double_top", -0.8))

        # Double bottom
        trough_indices = [i for i in range(1, len(recent_lows) - 1)
                          if recent_lows[i] < recent_lows[i-1] and recent_lows[i] < recent_lows[i+1]]
        if len(trough_indices) >= 2:
            t1, t2 = trough_indices[-2], trough_indices[-1]
            if abs(recent_lows[t1] - recent_lows[t2]) / max(recent_lows[t1], 1e-9) < 0.01:
                peak_between = max(recent_highs[t1:t2+1]) if t2 > t1 else 0
                if peak_between > recent_lows[t1] * 1.02:
                    patterns.append(("double_bottom", 0.8))

        # --- Flag / Pennant (continuation) ---
        # Strong move followed by tight consolidation
        if n >= 20:
            pole = closes[-20] - closes[-30] if n >= 30 else closes[-20] - closes[0]
            pole_pct = pole / closes[-30] * 100 if n >= 30 and closes[-30] != 0 else 0
            flag_range = max(highs[-10:]) - min(lows[-10:])
            flag_pct = flag_range / closes[-1] * 100 if closes[-1] != 0 else 999

            if abs(pole_pct) > 5 and flag_pct < 2:
                direction = 0.6 if pole_pct > 0 else -0.6
                patterns.append(("flag_continuation", direction))

        # --- Ascending / Descending Triangle ---
        if n >= 20:
            r_highs = highs[-20:]
            r_lows = lows[-20:]
            # Flat top + rising lows = ascending triangle (bullish)
            top_range = max(r_highs) - min(r_highs[-5:])
            low_slope = (min(r_lows[-5:]) - min(r_lows[:5])) / max(min(r_lows[:5]), 1e-9)
            if top_range / max(max(r_highs), 1e-9) < 0.01 and low_slope > 0.02:
                patterns.append(("ascending_triangle", 0.7))
            # Flat bottom + falling highs = descending triangle (bearish)
            bot_range = max(r_lows[-5:]) - min(r_lows)
            high_slope = (max(r_highs[-5:]) - max(r_highs[:5])) / max(max(r_highs[:5]), 1e-9)
            if bot_range / max(min(r_lows), 1e-9) < 0.01 and high_slope < -0.02:
                patterns.append(("descending_triangle", -0.7))

        # --- Engulfing candles (reversal) ---
        if n >= 2:
            prev_body = closes[-2] - candles[-2].open
            curr_body = closes[-1] - candles[-1].open
            if prev_body < 0 and curr_body > 0 and curr_body > abs(prev_body) * 1.5:
                patterns.append(("bullish_engulfing", 0.5))
            elif prev_body > 0 and curr_body < 0 and abs(curr_body) > prev_body * 1.5:
                patterns.append(("bearish_engulfing", -0.5))

        if not patterns:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.3,
                reason="no chart patterns detected in recent price action",
                evidence={"patterns_checked": 6, "patterns_found": 0},
            )

        score = sum(s for _, s in patterns) / len(patterns) * 100.0
        signs = [1 if s > 0 else -1 if s < 0 else 0 for _, s in patterns]
        pos = sum(1 for x in signs if x > 0)
        neg = sum(1 for x in signs if x < 0)
        confidence = max(pos, neg) / len(signals) if (signals := signs) else 0.0

        pattern_names = [name for name, _ in patterns]

        if score > 15:
            status = GateStatus.PASS
            reason = f"bullish patterns: {', '.join(pattern_names)}"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"bearish patterns: {', '.join(pattern_names)}"
        else:
            status = GateStatus.NEUTRAL
            reason = f"mixed patterns: {', '.join(pattern_names)}"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "patterns_detected": pattern_names,
                "sub_signals": {k: round(v, 4) for k, v in patterns},
            },
        )

"""Orderbook microstructure gate (spec 03, gate 4).

Aggregated depth, bid/ask imbalance, wall/spoofing/iceberg heuristics.
Deterministic computation only.
"""
from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class OrderbookMicroGate:
    name = "orderbook_micro"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        ob = ctx.order_book
        if not ob:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient data: no orderbook snapshot",
            )

        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        if not bids or not asks:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient data: empty orderbook sides",
            )

        # Parse levels: [[price, qty], ...] or [{price, amount}, ...]
        def _parse_levels(levels: list) -> list[tuple[float, float]]:
            out = []
            for lvl in levels[:20]:
                if isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
                    out.append((float(lvl[0]), float(lvl[1])))
                elif isinstance(lvl, dict):
                    p = float(lvl.get("price", lvl.get("p", 0)))
                    q = float(lvl.get("amount", lvl.get("qty", lvl.get("q", 0))))
                    out.append((p, q))
            return out

        bid_levels = _parse_levels(bids)
        ask_levels = _parse_levels(asks)
        if not bid_levels or not ask_levels:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient data: unparseable orderbook",
            )

        bid_depth = sum(q for _, q in bid_levels)
        ask_depth = sum(q for _, q in ask_levels)
        total_depth = bid_depth + ask_depth

        if total_depth == 0:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="insufficient data: zero depth",
            )

        signals: list[tuple[str, float]] = []

        # 1. Bid/ask imbalance: >0.6 bid-heavy = bullish support
        bid_ratio = bid_depth / total_depth
        if bid_ratio > 0.6:
            signals.append(("bid_heavy", (bid_ratio - 0.5) * 4.0))
        elif bid_ratio < 0.4:
            signals.append(("ask_heavy", (bid_ratio - 0.5) * 4.0))
        else:
            signals.append(("balanced_book", 0.0))

        # 2. Wall detection: single level > 30% of its side's depth
        max_bid = max(q for _, q in bid_levels)
        max_ask = max(q for _, q in ask_levels)
        if bid_depth > 0 and max_bid / bid_depth > 0.3:
            signals.append(("bid_wall", 0.6))
        if ask_depth > 0 and max_ask / ask_depth > 0.3:
            signals.append(("ask_wall", -0.6))

        # 3. Spread tightness: tight spread = healthy market
        best_bid = bid_levels[0][0]
        best_ask = ask_levels[0][0]
        mid = (best_bid + best_ask) / 2
        spread_pct = (best_ask - best_bid) / mid * 100 if mid > 0 else 999
        if spread_pct < 0.05:
            signals.append(("tight_spread", 0.2))
        elif spread_pct > 0.3:
            signals.append(("wide_spread", -0.3))
        else:
            signals.append(("normal_spread", 0.0))

        # 4. Depth slope: are deeper levels stacking up (support/resistance)?
        if len(bid_levels) >= 5:
            near_bid = sum(q for _, q in bid_levels[:5])
            far_bid = sum(q for _, q in bid_levels[5:])
            if far_bid > near_bid * 2:
                signals.append(("deep_bid_support", 0.4))
        if len(ask_levels) >= 5:
            near_ask = sum(q for _, q in ask_levels[:5])
            far_ask = sum(q for _, q in ask_levels[5:])
            if far_ask > near_ask * 2:
                signals.append(("deep_ask_resistance", -0.4))

        score = sum(s for _, s in signals) / max(len(signals), 1) * 100.0
        signs = [1 if s > 0 else -1 if s < 0 else 0 for _, s in signals]
        pos = sum(1 for x in signs if x > 0)
        neg = sum(1 for x in signs if x < 0)
        confidence = max(pos, neg) / len(signals) if signs else 0.0

        if score > 15:
            status = GateStatus.PASS
            reason = f"orderbook bullish (bid ratio={bid_ratio:.2f}, spread={spread_pct:.3f}%)"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"orderbook bearish (bid ratio={bid_ratio:.2f}, spread={spread_pct:.3f}%)"
        else:
            status = GateStatus.NEUTRAL
            reason = f"orderbook neutral (bid ratio={bid_ratio:.2f}, spread={spread_pct:.3f}%)"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=confidence,
            reason=reason,
            evidence={
                "bid_depth": round(bid_depth, 4),
                "ask_depth": round(ask_depth, 4),
                "bid_ratio": round(bid_ratio, 4),
                "spread_pct": round(spread_pct, 4),
                "max_bid_level": round(max_bid, 4),
                "max_ask_level": round(max_ask, 4),
                "sub_signals": {k: round(v, 4) for k, v in signals},
            },
        )

"""Fundamental context gate.

For spot crypto without access to order flow or news services, this
gate primarily inspects the order book (bid/ask depth) when available
and the symbol's listed tick size / min qty. With no order book data
the gate returns NEUTRAL with low confidence — it does not pretend to
know things it doesn't.
"""

from __future__ import annotations

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


class FundamentalContextGate:
    name = "fundamental_context"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        ob = ctx.order_book
        meta = ctx.symbol_meta

        if not ob:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.2,
                reason="no order book snapshot; context is unobservable",
                evidence={"order_book": None},
            )

        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids or not asks:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="order book empty",
            )

        # Imbalance: bid depth / ask depth in the top 20 levels.
        depth = 20
        bid_depth = sum(float(b[1]) for b in bids[:depth])
        ask_depth = sum(float(a[1]) for a in asks[:depth])
        if ask_depth <= 0:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason="zero ask depth",
            )
        imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

        score = max(min(imbalance * 100.0, 100.0), -100.0)
        if score > 15:
            status = GateStatus.PASS
            reason = f"bid-heavy book (imbalance {imbalance:+.2%})"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"ask-heavy book (imbalance {imbalance:+.2%})"
        else:
            status = GateStatus.NEUTRAL
            reason = f"balanced book (imbalance {imbalance:+.2%})"

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=0.5,
            reason=reason,
            evidence={
                "bid_depth": round(bid_depth, 4),
                "ask_depth": round(ask_depth, 4),
                "imbalance": round(imbalance, 4),
                "tick_size": meta.get("tick_size"),
                "min_qty": meta.get("min_qty"),
            },
        )

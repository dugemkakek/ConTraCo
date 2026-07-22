"""Fundamental context gate — orderbook depth + news sentiment.

Combines two signals:
  1. Orderbook bid/ask imbalance (micro-structure)
  2. RSS/news sentiment via VADER (macro narrative)

Both are free, no API key. The gate returns a weighted composite.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation

logger = logging.getLogger(__name__)


class FundamentalContextGate:
    name = "fundamental_context"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        ob = ctx.order_book
        meta = ctx.symbol_meta

        signals: list[tuple[str, float, float]] = []  # (name, score, weight)
        evidence: dict[str, Any] = {}

        # ── Signal 1: Orderbook imbalance ──
        if ob:
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and asks:
                depth = 20
                bid_depth = sum(float(b[1]) for b in bids[:depth])
                ask_depth = sum(float(a[1]) for a in asks[:depth])
                total_depth = bid_depth + ask_depth
                if total_depth > 0:
                    imbalance = (bid_depth - ask_depth) / total_depth
                    ob_score = max(min(imbalance * 100.0, 100.0), -100.0)
                    signals.append(("orderbook_imbalance", ob_score, 0.4))
                    evidence["bid_depth"] = round(bid_depth, 4)
                    evidence["ask_depth"] = round(ask_depth, 4)
                    evidence["imbalance"] = round(imbalance, 4)

        # ── Signal 2: News sentiment ──
        try:
            from app.services.fundamentals.news_aggregator import get_news_context
            news = await get_news_context(ctx.symbol, max_age_hours=12.0, max_items=20)
            sentiment = news.get("sentiment", {})
            macro = news.get("macro_sentiment", {})

            compound = sentiment.get("mean_compound", 0.0)
            news_score = max(min(compound * 200.0, 100.0), -100.0)  # scale [-0.5,0.5] → [-100,100]
            signals.append(("news_sentiment", news_score, 0.35))

            macro_compound = macro.get("mean_compound", 0.0)
            macro_score = max(min(macro_compound * 200.0, 100.0), -100.0)
            signals.append(("macro_sentiment", macro_score, 0.25))

            evidence["news"] = {
                "sentiment_label": sentiment.get("label"),
                "mean_compound": compound,
                "bullish": sentiment.get("bullish_count", 0),
                "bearish": sentiment.get("bearish_count", 0),
                "total_articles": sentiment.get("total", 0),
                "macro_label": macro.get("label"),
                "macro_compound": macro_compound,
                "top_headlines": [a["title"] for a in news.get("articles", [])[:3]],
            }
        except Exception as exc:
            logger.debug("News sentiment unavailable: %s", exc)
            evidence["news"] = {"error": str(exc)}

        # ── Composite ──
        if not signals:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.NEUTRAL,
                score=0.0,
                confidence=0.1,
                reason="no fundamental data available",
                evidence=evidence,
            )

        total_weight = sum(w for _, _, w in signals)
        score = sum(s * w for _, s, w in signals) / total_weight if total_weight > 0 else 0.0
        score = max(min(score, 100.0), -100.0)

        if score > 15:
            status = GateStatus.PASS
            reason = f"fundamentals bullish (composite {score:+.1f})"
        elif score < -15:
            status = GateStatus.FAIL
            reason = f"fundamentals bearish (composite {score:+.1f})"
        else:
            status = GateStatus.NEUTRAL
            reason = f"fundamentals neutral (composite {score:+.1f})"

        evidence["sub_signals"] = {k: round(v, 2) for k, v, _ in signals}
        evidence["tick_size"] = meta.get("tick_size") if meta else None
        evidence["min_qty"] = meta.get("min_qty") if meta else None

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=min(0.5 + 0.1 * len(signals), 0.8),
            reason=reason,
            evidence=evidence,
        )

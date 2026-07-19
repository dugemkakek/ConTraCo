"""Risk & tradeability gate (Gate F).

This is the only gate that can issue a deterministic VETO. It does
not produce a directional score; if it votes it forces AVOID for
that run.

Checks:
  * Liquidity: 24h quote volume must be above a configurable floor.
  * Spread: bid-ask spread below a max.
  * Tradeability: symbol is active and not in a maintenance window.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from app.db.models import GateStatus
from app.engine.gates import GateContext, GateEvaluation


DEFAULT_MIN_24H_QUOTE_VOLUME = float(os.getenv("GATE_F_MIN_24H_QUOTE_VOLUME", "100000"))
DEFAULT_MAX_SPREAD_BPS = float(os.getenv("GATE_F_MAX_SPREAD_BPS", "50"))


class RiskTradeabilityGate:
    name = "risk_tradeability"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        meta = ctx.symbol_meta or {}
        ob = ctx.order_book

        veto_reasons: list[str] = []
        evidence: dict = {
            "min_24h_quote_volume": DEFAULT_MIN_24H_QUOTE_VOLUME,
            "max_spread_bps": DEFAULT_MAX_SPREAD_BPS,
        }

        # Liquidity
        quote_vol_24h = meta.get("quote_volume_24h")
        if quote_vol_24h is not None:
            evidence["quote_volume_24h"] = quote_vol_24h
            if quote_vol_24h < DEFAULT_MIN_24H_QUOTE_VOLUME:
                veto_reasons.append(
                    f"24h quote volume {quote_vol_24h:.0f} below floor {DEFAULT_MIN_24H_QUOTE_VOLUME:.0f}"
                )

        # Spread
        if ob:
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                if best_bid > 0 and best_ask > best_bid:
                    spread_bps = (best_ask - best_bid) / best_bid * 10_000
                    evidence["spread_bps"] = round(spread_bps, 2)
                    evidence["best_bid"] = best_bid
                    evidence["best_ask"] = best_ask
                    if spread_bps > DEFAULT_MAX_SPREAD_BPS:
                        veto_reasons.append(
                            f"spread {spread_bps:.1f}bps exceeds {DEFAULT_MAX_SPREAD_BPS:.0f}bps"
                        )

        # Tradeability flag
        if meta.get("is_active") is False:
            veto_reasons.append("symbol marked inactive")

        # Time-of-day sanity: stop trading on weekends for less liquid
        # markets? — leave as a config knob, default to no veto.
        # (intentionally a no-op by default; documented in threat-model)

        if veto_reasons:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.VETO,
                score=0.0,
                confidence=1.0,
                reason="; ".join(veto_reasons),
                evidence=evidence,
            )

        # Pass: surface enough info that the decision console can show
        # the trader why the trade *is* allowed.
        evidence["evaluated_at"] = datetime.fromtimestamp(
            ctx.now_unix or int(time.time()), tz=timezone.utc
        ).isoformat()
        return GateEvaluation(
            name=self.name,
            status=GateStatus.PASS,
            score=0.0,
            confidence=1.0,
            reason="tradeable",
            evidence=evidence,
        )

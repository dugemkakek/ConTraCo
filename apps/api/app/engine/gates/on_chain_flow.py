"""On-Chain Flow Gate — evaluates exchange concentration, volume, and network health.

Uses free public APIs (CoinGecko, blockchain.info) — no API key required.
Replaces the Phase-14 mock with real on-chain proxy signals.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.models import GateStatus
from app.engine.gates import BaseGate, GateContext, GateEvaluation
from app.services.onchain import get_onchain_metrics, get_btc_network_stats

logger = logging.getLogger(__name__)


class OnChainFlowGate(BaseGate):
    name = "on_chain_flow"

    async def evaluate(self, ctx: GateContext) -> GateEvaluation:
        """Evaluate on-chain metrics: exchange concentration, volume, network health."""
        symbol = ctx.symbol.upper()
        base = symbol.split("/")[0] if "/" in symbol else symbol

        metrics = await get_onchain_metrics(symbol)
        if metrics is None:
            return GateEvaluation(
                name=self.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason=f"no on-chain data available for {base}",
            )

        score = 0.0
        reasons: list[str] = []
        evidence: dict[str, Any] = {"source": metrics["source"]}

        # 1. Exchange concentration: high top-exchange share = fragile
        top_share = metrics.get("top_exchange_share_pct", 0)
        exchange_count = metrics.get("exchange_count", 0)
        evidence["top_exchange_share_pct"] = top_share
        evidence["exchange_count"] = exchange_count

        if top_share > 60:
            score -= 10.0
            reasons.append(f"high exchange concentration ({top_share:.0f}% on top venue)")
        elif top_share > 40:
            score -= 3.0
            reasons.append(f"moderate concentration ({top_share:.0f}%)")
        elif exchange_count >= 10:
            score += 5.0
            reasons.append(f"well-distributed ({exchange_count} exchanges)")

        # 2. Price momentum (24h change as flow proxy)
        change_24h = metrics.get("price_change_24h_pct")
        if change_24h is not None:
            evidence["price_change_24h_pct"] = round(change_24h, 2)
            if change_24h > 5:
                score += 10.0
                reasons.append(f"strong 24h inflow momentum (+{change_24h:.1f}%)")
            elif change_24h > 1:
                score += 3.0
                reasons.append(f"moderate inflow (+{change_24h:.1f}%)")
            elif change_24h < -5:
                score -= 10.0
                reasons.append(f"strong 24h outflow momentum ({change_24h:.1f}%)")
            elif change_24h < -1:
                score -= 3.0
                reasons.append(f"moderate outflow ({change_24h:.1f}%)")

        # 3. ATH distance — deep drawdown = potential capitulation / accumulation
        ath_change = metrics.get("ath_change_pct")
        if ath_change is not None:
            evidence["ath_change_pct"] = round(ath_change, 1)
            if ath_change < -80:
                score += 5.0
                reasons.append(f"deep drawdown from ATH ({ath_change:.0f}%) — accumulation zone")
            elif ath_change < -50:
                score += 2.0
                reasons.append(f"significant drawdown ({ath_change:.0f}% from ATH)")

        # 4. BTC-specific: network health (hash rate, mempool)
        if base == "BTC":
            btc_stats = await get_btc_network_stats()
            if btc_stats:
                evidence["btc_network"] = btc_stats
                mempool = btc_stats.get("mempool_size", 0)
                if mempool and mempool > 300_000:
                    score -= 3.0
                    reasons.append(f"BTC mempool congested ({mempool:,} txs)")
                elif mempool and mempool < 50_000:
                    score += 2.0
                    reasons.append(f"BTC mempool clear ({mempool:,} txs)")

        score = max(-100.0, min(100.0, score))

        if score >= 15:
            status = GateStatus.PASS
        elif score <= -15:
            status = GateStatus.FAIL
        elif abs(score) < 5:
            status = GateStatus.NEUTRAL
        else:
            status = GateStatus.WARN

        return GateEvaluation(
            name=self.name,
            status=status,
            score=score,
            confidence=0.7 if metrics else 0.0,
            reason="; ".join(reasons) if reasons else "no significant on-chain signal",
            evidence=evidence,
        )

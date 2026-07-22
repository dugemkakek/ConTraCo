"""Multi-Timeframe Confluence (MTC) engine.

Runs the standard gate pipeline across 3 timeframes (e.g., 4H, 1H, 15m)
and produces a combined MTC score that weights HTF/MTF/LTF alignment.

Entry point: ``run_mtc_analysis(db, user, symbol, timeframes, ...)``
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    Decision as DecisionRow,
    Direction,
    FinalState,
    GateResult,
    ModelOpinion as ModelOpinionRow,
    ModelStatus,
    RunStatus,
    TradePlan,
    User,
)
from app.engine.council import CouncilContext, ModelOpinionData, run_council
from app.engine.decision import decide
from app.engine.gates import ALL_GATES, GateContext, GateEvaluation
from app.engine.strategy import StrategyConfigSpec, get_active_spec
from app.engine.trade_plan import build_plan
from app.services.fundamentals.context_builder import build_context
from app.services.market_data.factory import build_provider

logger = logging.getLogger(__name__)

# Default MTC timeframes — HTF, MTF, LTF
DEFAULT_MTF_TIMEFRAMES = ["4h", "1h", "15m"]


@dataclass
class MTFResult:
    """Per-timeframe gate results."""
    timeframe: str
    candles: list
    gate_evals: list[GateEvaluation]
    gate_error: str | None = None


@dataclass
class MTCContext:
    """Multi-timeframe council context."""
    symbol: str
    timeframes: list[str]
    mtf_results: list[MTFResult]
    symbol_meta: dict = field(default_factory=dict)
    order_book: dict | None = None
    fundamental_context: str = ""


async def _fetch_and_gate(
    symbol: str, timeframe: str, candle_limit: int
) -> MTFResult:
    """Fetch candles and run all gates for a single timeframe."""
    provider = build_provider()
    try:
        candles = await provider.get_ohlcv(symbol, timeframe, limit=candle_limit)
    except Exception as exc:
        logger.warning("MTC: candles failed for %s %s: %s", symbol, timeframe, exc)
        return MTFResult(timeframe=timeframe, candles=[], gate_evals=[], gate_error=str(exc))

    if not candles:
        return MTFResult(timeframe=timeframe, candles=[], gate_evals=[],
                         gate_error="no candle data")

    gctx = GateContext(symbol=symbol, timeframe=timeframe, candles=candles)
    gate_evals: list[GateEvaluation] = []
    for gate in ALL_GATES:
        try:
            ev = await gate.evaluate(gctx)
        except Exception as exc:
            logger.exception("MTC gate %s crashed on %s %s", gate.name, symbol, timeframe)
            gate_evals.append(GateEvaluation(
                name=gate.name,
                status="UNAVAILABLE",
                score=0.0,
                confidence=0.0,
                reason=f"gate crashed: {exc}",
            ))
            continue
        gate_evals.append(GateEvaluation(
            name=ev.name,
            status=ev.status,
            score=ev.score,
            confidence=ev.confidence,
            reason=ev.reason,
            evidence=dict(ev.evidence) if ev.evidence else {},
        ))

    return MTFResult(timeframe=timeframe, candles=candles, gate_evals=gate_evals)


def _compute_mtc_score(results: list[MTFResult]) -> dict[str, float]:
    """Compute a simple MTC alignment score.

    Returns a dict with:
      - mtc_score: overall alignment [-100, 100]
      - htf_bias: HTF directional bias
      - mtf_bias: MTF directional bias
      - ltf_bias: LTF directional bias
      - alignment: 0..1 how well the timeframes agree
    """
    if len(results) < 2:
        return {"mtc_score": 0.0, "htf_bias": 0.0, "mtf_bias": 0.0,
                "ltf_bias": 0.0, "alignment": 0.0}

    def _bias(r: MTFResult) -> float:
        if not r.gate_evals:
            return 0.0
        directional = [g for g in r.gate_evals if g.is_directional()]
        if not directional:
            return 0.0
        return sum(g.score for g in directional) / len(directional)

    biases = [(r.timeframe, _bias(r)) for r in results]
    # Weight: HTF=0.5, MTF=0.3, LTF=0.2
    weights = {"4h": 0.5, "1h": 0.3, "15m": 0.2, "1d": 0.5, "30m": 0.25, "5m": 0.15}
    total_w = 0.0
    weighted = 0.0
    for tf, bias in biases:
        w = weights.get(tf, 0.25)
        weighted += bias * w
        total_w += w

    mtc = (weighted / total_w) if total_w > 0 else 0.0

    # Alignment: are all signs the same?
    signs = [1.0 if b > 5 else -1.0 if b < -5 else 0.0 for _, b in biases]
    if all(s == 1.0 for s in signs) or all(s == -1.0 for s in signs):
        alignment = 1.0
    elif all(s == 0.0 for s in signs):
        alignment = 0.0
    else:
        # Count matching signs
        majority = 1.0 if sum(1 for s in signs if s == 1.0) >= len(signs) / 2 else -1.0
        if majority == 0:
            alignment = 0.0
        else:
            alignment = sum(1.0 for s in signs if s == majority) / len(signs)

    bias_map = {}
    for tf, b in biases:
        if tf in ("4h", "1d"):
            bias_map["htf_bias"] = b
        elif tf in ("1h", "30m"):
            bias_map["mtf_bias"] = b
        elif tf in ("15m", "5m"):
            bias_map["ltf_bias"] = b

    return {
        "mtc_score": round(mtc, 1),
        "htf_bias": round(bias_map.get("htf_bias", 0.0), 1),
        "mtf_bias": round(bias_map.get("mtf_bias", 0.0), 1),
        "ltf_bias": round(bias_map.get("ltf_bias", 0.0), 1),
        "alignment": round(alignment, 2),
    }


async def run_mtc_analysis(
    db: Session,
    *,
    user: User,
    symbol: str,
    timeframes: list[str] | None = None,
    strategy_name: str = "balanced",
    candle_limit: int = 300,
    config_id: int | None = None,
) -> AnalysisRun:
    """Run full multi-timeframe analysis and persist everything."""
    if timeframes is None:
        timeframes = DEFAULT_MTF_TIMEFRAMES

    config_id, spec = (
        (config_id, _spec_from_id(db, config_id))
        if config_id
        else get_active_spec(db, name=strategy_name)
    )

    tf_str = ",".join(timeframes)
    run = AnalysisRun(
        user_id=user.id,
        symbol=symbol.upper(),
        timeframe=tf_str,
        config_id=config_id,
        status=RunStatus.RUNNING,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    db.refresh(user)

    try:
        # 1) Fetch candles + run gates for all timeframes concurrently
        mtf_results = await asyncio.gather(*[
            _fetch_and_gate(symbol, tf, candle_limit) for tf in timeframes
        ])

        # 2) Persist gate results for all timeframes
        for mr in mtf_results:
            for ge in mr.gate_evals:
                db.add(GateResult(
                    run_id=run.id,
                    gate_name=f"{mr.timeframe}:{ge.name}",
                    status=ge.status,
                    score=ge.score,
                    weight=spec.gates.model_dump().get(ge.name, 0.0),
                    confidence=ge.confidence,
                    reason=ge.reason,
                    evidence=dict(ge.evidence) if ge.evidence else {},
                ))

        # 3) Build fundamental context
        fc = await build_context(db, symbol)

        # 4) Flatten gate evals for the council (all timeframes)
        all_gate_evals = []
        for mr in mtf_results:
            all_gate_evals.extend(mr.gate_evals)

        # 5) Build MTC context and run council
        mtc_ctx = MTCContext(
            symbol=symbol,
            timeframes=timeframes,
            mtf_results=mtf_results,
            order_book=None,
            fundamental_context=fc,
        )

        # Use the primary timeframe's candles for the council context
        primary = mtf_results[0] if mtf_results else None
        council_ctx = CouncilContext(
            symbol=symbol,
            timeframe=tf_str,
            candles=primary.candles if primary else [],
            gates=all_gate_evals,
            fundamental_context=fc,
        )

        opinions = await run_council(council_ctx)
        for o in opinions:
            db.add(ModelOpinionRow(
                run_id=run.id,
                role=o.role,
                status=o.status,
                direction=o.direction,
                confidence=o.confidence,
                role_weight=o.role_weight,
                confidence_cap=o.confidence_cap,
                evidence_ids=list(o.evidence_ids),
                risk_flags=list(o.risk_flags),
                raw_output={
                    "reason": o.reason,
                    "provider_used": getattr(o, "provider_used", "unknown"),
                    "llm_model": getattr(o, "llm_model", ""),
                },
                reason=o.reason,
            ))

        # 6) Decision
        result = decide(
            gates=all_gate_evals,
            opinions=opinions,
            spec=spec,
            total_configured_gates=len(ALL_GATES),
            total_directional_roles=4,
        )

        # 7) Compute MTC alignment score
        mtc_scores = _compute_mtc_score(mtf_results)

        run.final_state = result.final_state
        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        run.note = (
            f"MTC: {len(timeframes)} timeframes ({tf_str}). "
            f"Alignment: {mtc_scores['alignment']:.0%}. "
            f"Bias: HTF={mtc_scores['htf_bias']:+.1f} "
            f"MTF={mtc_scores['mtf_bias']:+.1f} "
            f"LTF={mtc_scores['ltf_bias']:+.1f}"
        )
        db.add(DecisionRow(
            run_id=run.id,
            final_state=result.final_state,
            gate_score=result.gate_score,
            model_score=result.model_score,
            composite_score=result.composite_score,
            model_agreement=result.model_agreement,
            data_completeness=result.data_completeness,
            model_completeness=result.model_completeness,
            vetoes=result.vetoes,
            veto_sources=result.veto_sources,
            reason=f"{result.reason} | MTC: alignment={mtc_scores['alignment']:.0%}",
        ))

        # 8) Trade plan
        plan = build_plan(
            symbol=symbol, timeframe=tf_str,
            candles=primary.candles if primary else [],
            final_state=result.final_state, decision=result,
            spec_min_rr=spec.minimum_risk_reward,
            spec_max_stop_atr=spec.maximum_stop_atr_multiple,
        )
        if plan is not None:
            db.add(TradePlan(
                run_id=run.id,
                direction=plan.direction,
                entry_price=plan.entry_price,
                stop_price=plan.stop_price,
                take_profit=plan.take_profit,
                risk_reward=plan.risk_reward,
                position_size_pct=plan.position_size_pct,
                invalidation=plan.invalidation,
                risk_review=plan.risk_review,
                synthesis=plan.synthesis,
            ))

        db.commit()

    except Exception as exc:
        logger.exception("MTC analysis failed for %s", symbol)
        run.status = RunStatus.FAILED
        run.note = f"mtc runner exception: {exc}"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

    db.refresh(run)
    return run


def _spec_from_id(db: Session, config_id: int) -> StrategyConfigSpec:
    from app.db.models import StrategyConfig  # noqa: PLC0415
    row = db.get(StrategyConfig, config_id)
    if row is None:
        raise ValueError(f"unknown strategy config id {config_id}")
    return StrategyConfigSpec.model_validate({**row.payload, "name": row.name})
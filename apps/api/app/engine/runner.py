"""Analysis runner.

Orchestrates the end-to-end flow:
  1. fetch candles (and order book, if available) from the provider
  2. run all 6 deterministic gates
  3. run the AI council
  4. call the decision engine
  5. (if applicable) build the trade plan + risk + synthesis
  6. persist the run, gates, opinions, decision, and plan
  7. emit a Redis alert on notable final states

Public entry points:
  * ``run_analysis(...)`` — returns a fully-persisted ``AnalysisRun``
    with all child rows attached.
  * ``get_run(...)`` — fetch a run by id for the API
  * ``list_runs(...)`` — paginated list
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Alert,
    AlertSeverity,
    AnalysisRun,
    Decision as DecisionRow,
    Direction,
    FinalState,
    GateResult,
    GateStatus,
    ModelOpinion as ModelOpinionRow,
    ModelStatus,
    RunStatus,
    TradePlan,
    User,
)
from app.engine.confluence import (
    GateVerdict,
    MarketRegime,
    detect_regime,
    run_confluence,
)
from app.engine.council import CouncilContext, ModelOpinionData, run_council
from app.engine.debate import run_debate
from app.engine.decision import decide
from app.engine.gates import ALL_GATES, GateContext, GateEvaluation
from app.engine.strategy import StrategyConfigSpec, get_active_spec
from app.engine.trade_plan import build_plan
from app.db import redis_client
from app.services.market_data.factory import build_provider
from app.services.market_data.registry import all_providers
from app.services.market_data.snapshot import MarketSnapshot, MarketSnapshotPipeline, SnapshotCache
from app.services.fundamentals.context_builder import build_context

logger = logging.getLogger(__name__)


async def _fetch_market_data(symbol: str, timeframe: str, limit: int) -> MarketSnapshot:
    """Build one canonical, cached snapshot with provider failover."""
    primary = build_provider()
    providers = [primary]
    if primary.name != "mock":
        providers.extend(
            p for p in all_providers()
            if p.name not in {primary.name, "mock"}
            and p.is_symbol_supported(symbol)
            and p.is_timeframe_supported(timeframe)
        )
    cache = SnapshotCache(await redis_client.get_redis())
    return await MarketSnapshotPipeline(providers, cache).build(
        symbol, timeframe, limit=limit
    )


async def run_analysis(
    db: Session,
    *,
    user: User,
    symbol: str,
    timeframe: str,
    strategy_name: str = "balanced",
    candle_limit: int = 300,
    config_id: int | None = None,
) -> AnalysisRun:
    """Run a full analysis and persist everything."""
    config_id, spec = (
        (config_id, _spec_from_id(db, config_id))
        if config_id
        else get_active_spec(db, name=strategy_name)
    )

    run = AnalysisRun(
        user_id=user.id,
        symbol=symbol.upper(),
        timeframe=timeframe,
        config_id=config_id,
        status=RunStatus.RUNNING,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    # After commit, refresh user too so any expired attributes are rehydrated.
    db.refresh(user)

    try:
        # 1) data
        snapshot = await _fetch_market_data(symbol, timeframe, candle_limit)
        candles, order_book = snapshot.candles, snapshot.order_book
        if not candles:
            run.status = RunStatus.COMPLETED
            run.final_state = FinalState.DATA_INVALID
            run.completed_at = datetime.now(timezone.utc)
            run.note = "no candle data from provider"
            db.commit()
            return run

        # 2) gates
        symbol_meta: dict[str, Any] = snapshot.symbol_meta
        symbol_meta["quote_volume_24h"] = (
            order_book.get("quote_volume_24h") if order_book else None
        )
        gctx = GateContext(
            symbol=symbol, timeframe=timeframe, candles=candles,
            order_book=order_book, symbol_meta=symbol_meta,
        )
        gate_evals = []
        for gate in ALL_GATES:
            try:
                ev = await gate.evaluate(gctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("gate %s crashed", gate.name)
                ev = type("E", (), {})()  # type: ignore[assignment]
                ev.name = gate.name
                ev.status = GateStatus.UNAVAILABLE
                ev.score = 0.0
                ev.confidence = 0.0
                ev.reason = f"gate crashed: {exc}"
                ev.evidence = {}
            from app.engine.gates import GateEvaluation  # local import for typing
            ge = GateEvaluation(
                name=ev.name, status=ev.status, score=ev.score,
                confidence=ev.confidence, reason=ev.reason, evidence=dict(ev.evidence) if ev.evidence else {},
            )
            gate_evals.append(ge)
            db.add(
                GateResult(
                    run_id=run.id,
                    gate_name=ge.name,
                    status=ge.status,
                    score=ge.score,
                    weight=spec.gates.model_dump().get(ge.name, 0.0),
                    confidence=ge.confidence,
                    reason=ge.reason,
                    evidence=dict(ge.evidence) if ge.evidence else {},
                )
            )

        # 3) fundamental context for the LLM council
        fc = await build_context(db, symbol)

        # 3.5) Confluence engine (spec 04)
        # Bridge GateEvaluation → GateVerdict, detect regime, compute
        # confluence score + scenario framing + Kelly.
        regime = None
        for ge in gate_evals:
            if ge.name == "market_regime" and ge.status != GateStatus.UNAVAILABLE:
                adx_val = ge.evidence.get("adx", 0)
                # Estimate ATR% from candles
                if len(candles) >= 14:
                    atr_pct = sum(
                        c.high - c.low for c in candles[-14:]
                    ) / 14 / max(candles[-1].close, 1e-9) * 100
                else:
                    atr_pct = 0.0
                regime = detect_regime(adx_val, atr_pct)
                break

        verdicts: list[GateVerdict] = []
        for ge in gate_evals:
            if ge.status == GateStatus.UNAVAILABLE:
                continue
            w = spec.gates.model_dump().get(ge.name, 0.0)
            if w == 0.0:
                continue
            # Map gate score to direction: positive → +1, negative → -1
            direction = 1 if ge.score > 5 else -1 if ge.score < -5 else 0
            verdicts.append(GateVerdict(
                gate_name=ge.name,
                direction=direction,
                confidence=ge.confidence,
                weight=w,
                reasoning=ge.reason,
                evidence=ge.evidence,
            ))

        conf_result = run_confluence(
            verdicts,
            regime=regime,
            htf_direction=0,  # ponytail: wire MTF when multi-TF data pipeline exists
            mtf_direction=0,
            ltf_direction=0,
        )
        conf_dict = conf_result.to_dict()

        # 4) council
        council_ctx = CouncilContext(
            symbol=symbol, timeframe=timeframe, candles=candles,
            gates=gate_evals, order_book=order_book, symbol_meta=symbol_meta,
            fundamental_context=fc,
        )
        opinions = await run_council(council_ctx)
        for o in opinions:
            db.add(
                ModelOpinionRow(
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
                )
            )

        # 4.5) CRO debate protocol (spec 03)
        council_op_dicts = [
            {"role": o.role, "direction": o.direction.value,
             "confidence": o.confidence, "reason": o.reason}
            for o in opinions
        ]
        # The fundamental_context gate already fetched VADER-scored news
        # sentiment — reuse it in the debate instead of hitting the network
        # a second time.
        news_ev = next(
            (ge.evidence.get("news") for ge in gate_evals
             if ge.name == "fundamental_context"),
            None,
        )
        debate = run_debate(
            verdicts, conf_result.scenario, council_op_dicts,
            news_sentiment=news_ev,
        )
        conf_dict["debate"] = debate.to_dict()

        # 5) decision
        result = decide(
            gates=gate_evals,
            opinions=opinions,
            spec=spec,
            total_configured_gates=len(ALL_GATES),
            total_directional_roles=4,
        )
        run.final_state = result.final_state
        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        db.add(
            DecisionRow(
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
                reason=result.reason,
                confluence_result=conf_dict,
            )
        )

        # 5) trade plan (only on actionable final state)
        plan = build_plan(
            symbol=symbol, timeframe=timeframe, candles=candles,
            final_state=result.final_state, decision=result,
            spec_min_rr=spec.minimum_risk_reward,
            spec_max_stop_atr=spec.maximum_stop_atr_multiple,
        )
        if plan is not None:
            db.add(
                TradePlan(
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
                )
            )

        # 6) alerts on notable final states
        if result.final_state in (FinalState.LONG_CANDIDATE, FinalState.SHORT_CANDIDATE):
            db.add(
                Alert(
                    user_id=user.id,
                    symbol=symbol,
                    severity=AlertSeverity.INFO,
                    message=f"{result.final_state.value} on {symbol} {timeframe} "
                            f"(composite {result.composite_score:+.1f})",
                )
            )
        elif result.final_state == FinalState.AVOID and result.vetoes:
            db.add(
                Alert(
                    user_id=user.id,
                    symbol=symbol,
                    severity=AlertSeverity.WARNING,
                    message=f"AVOID on {symbol} {timeframe}: {'; '.join(result.vetoes[:3])}",
                )
            )

        db.commit()

        # 7) WebSocket broadcast on notable final states — soft fail
        try:
            from app.services.realtime.ws_hub import manager as _ws
            await _ws.broadcast_to_user(
                str(user.id),
                {
                    "type": "analysis_complete",
                    "run_id": run.id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "final_state": (result.final_state.value if result.final_state else None),
                    "composite_score": result.composite_score,
                },
            )
        except Exception:  # noqa: BLE001
            pass

    except Exception as exc:  # noqa: BLE001
        logger.exception("analysis run failed for %s %s", symbol, timeframe)
        run.status = RunStatus.FAILED
        run.note = f"runner exception: {exc}"
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


def get_run(db: Session, run_id: int, user_id: int | None = None) -> AnalysisRun | None:
    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.id == run_id)
        .options(
            selectinload(AnalysisRun.gates),
            selectinload(AnalysisRun.opinions),
            selectinload(AnalysisRun.decision),
            selectinload(AnalysisRun.trade_plan),
            selectinload(AnalysisRun.config),
        )
    )
    if user_id is not None:
        stmt = stmt.where(AnalysisRun.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def list_runs(
    db: Session,
    *,
    user_id: int | None = None,
    symbol: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AnalysisRun]:
    stmt = (
        select(AnalysisRun)
        .options(selectinload(AnalysisRun.decision), selectinload(AnalysisRun.trade_plan))
        .order_by(desc(AnalysisRun.started_at))
        .limit(limit)
        .offset(offset)
    )
    if user_id is not None:
        stmt = stmt.where(AnalysisRun.user_id == user_id)
    if symbol:
        stmt = stmt.where(AnalysisRun.symbol == symbol.upper())
    return list(db.execute(stmt).scalars().all())


__all__ = ["run_analysis", "get_run", "list_runs"]

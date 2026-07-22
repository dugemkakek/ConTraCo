"""Analysis run API."""


from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import AnalysisRun, User
from app.engine.runner import get_run, list_runs, run_analysis

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class RunRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    strategy: str = "balanced"
    config_id: int | None = None
    candle_limit: int = 300


class DecisionOut(BaseModel):
    model_config = {"protected_namespaces": ()}
    final_state: str
    gate_score: float
    model_score: float
    composite_score: float
    model_agreement: float
    data_completeness: float
    model_completeness: float
    vetoes: list[str]
    veto_sources: list[str]
    reason: str
    confluence_result: dict[str, Any] | None = None


class GateOut(BaseModel):
    name: str
    status: str
    score: float
    weight: float
    confidence: float
    reason: str
    evidence: dict[str, Any]


class OpinionOut(BaseModel):
    role: str
    status: str
    direction: str
    confidence: float
    role_weight: float
    confidence_cap: float
    reason: str
    risk_flags: list[str]
    evidence_ids: list[str]


class TradePlanOut(BaseModel):
    direction: str
    entry_price: float | None
    stop_price: float | None
    take_profit: float | None
    risk_reward: float | None
    position_size_pct: float | None
    invalidation: str
    risk_review: str
    synthesis: str


class RunOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    status: str
    final_state: str | None
    config_id: int
    started_at: str
    completed_at: str | None
    note: str | None
    decision: DecisionOut | None
    gates: list[GateOut]
    opinions: list[OpinionOut]
    trade_plan: TradePlanOut | None


def _serialize(run: AnalysisRun) -> RunOut:
    d = run.decision
    return RunOut(
        id=run.id,
        symbol=run.symbol,
        timeframe=run.timeframe,
        status=run.status.value,
        final_state=run.final_state.value if run.final_state else None,
        config_id=run.config_id,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        note=run.note,
        decision=DecisionOut(
            final_state=d.final_state.value,
            gate_score=d.gate_score,
            model_score=d.model_score,
            composite_score=d.composite_score,
            model_agreement=d.model_agreement,
            data_completeness=d.data_completeness,
            model_completeness=d.model_completeness,
            vetoes=d.vetoes,
            veto_sources=d.veto_sources,
            reason=d.reason,
            confluence_result=d.confluence_result,
        ) if d else None,
        gates=[
            GateOut(
                name=g.gate_name, status=g.status.value, score=g.score,
                weight=g.weight, confidence=g.confidence, reason=g.reason,
                evidence=g.evidence,
            ) for g in run.gates
        ],
        opinions=[
            OpinionOut(
                role=o.role, status=o.status.value, direction=o.direction.value,
                confidence=o.confidence, role_weight=o.role_weight,
                confidence_cap=o.confidence_cap, reason=o.reason,
                risk_flags=o.risk_flags, evidence_ids=o.evidence_ids,
                provider_used=(o.raw_output or {}).get("provider_used", "unknown"),
                llm_model=(o.raw_output or {}).get("llm_model", ""),
            ) for o in run.opinions
        ],
        trade_plan=TradePlanOut(
            direction=p.direction.value, entry_price=p.entry_price,
            stop_price=p.stop_price, take_profit=p.take_profit,
            risk_reward=p.risk_reward, position_size_pct=p.position_size_pct,
            invalidation=p.invalidation, risk_review=p.risk_review,
            synthesis=p.synthesis,
        ) if run.trade_plan else None,
    )


@router.post("/run", response_model=RunOut)
async def post_run(
    body: RunRequest,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    run = await run_analysis(
        db,
        user=user,
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
        strategy_name=body.strategy,
        candle_limit=body.candle_limit,
        config_id=body.config_id,
    )
    full = get_run(db, run.id, user_id=user.id)
    if full is None:
        raise HTTPException(status_code=500, detail="run vanished after creation")
    return _serialize(full)


@router.get("/runs", response_model=list[RunOut])
def get_runs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = list_runs(db, user_id=user.id, symbol=symbol, limit=limit, offset=offset)
    # list_runs doesn't eager-load; do a per-row hydrate
    out: list[RunOut] = []
    for r in rows:
        full = get_run(db, r.id, user_id=user.id)
        if full is not None:
            out.append(_serialize(full))
    return out


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run_by_id(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    full = get_run(db, run_id, user_id=user.id)
    if full is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _serialize(full)


__all__ = ["router"]

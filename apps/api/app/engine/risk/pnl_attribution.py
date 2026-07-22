"""P&L attribution by gate.

Joins JournalEntry → AnalysisRun → GateResult to measure how often
each gate's directional call matched the actual trade outcome.

Accuracy per gate = (correct calls / total calls) where "correct"
means the gate's direction aligned with the trade's profitable side.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, GateResult, JournalEntry


@dataclass
class GateAttribution:
    gate_name: str
    total_trades: int = 0
    correct_calls: int = 0
    accuracy_pct: float = 0.0
    avg_confidence: float = 0.0
    pnl_when_correct: float = 0.0
    pnl_when_wrong: float = 0.0


@dataclass
class AttributionReport:
    total_closed_trades: int = 0
    total_pnl: float = 0.0
    gates: list[GateAttribution] = field(default_factory=list)


def compute_gate_attribution(
    db: Session,
    user_id: int,
    limit: int = 500,
) -> AttributionReport:
    """Compute per-gate accuracy from closed journal entries linked to analysis runs."""
    # Get closed journal entries with analysis_run_id
    entries = db.execute(
        select(JournalEntry)
        .where(JournalEntry.user_id == user_id)
        .where(JournalEntry.pnl.isnot(None))
        .where(JournalEntry.analysis_run_id.isnot(None))
        .order_by(JournalEntry.closed_at.desc())
        .limit(limit)
    ).scalars().all()

    if not entries:
        return AttributionReport()

    total_pnl = sum(e.pnl for e in entries if e.pnl)

    # Collect all run_ids
    run_ids = list({e.analysis_run_id for e in entries if e.analysis_run_id})
    if not run_ids:
        return AttributionReport(total_closed_trades=len(entries), total_pnl=round(total_pnl, 4))

    # Load gate results for those runs
    gate_rows = db.execute(
        select(GateResult)
        .where(GateResult.run_id.in_(run_ids))
    ).scalars().all()

    # Build run_id → {gate_name: (direction, confidence)}
    run_gates: dict[int, dict[str, tuple[str, float]]] = {}
    for g in gate_rows:
        run_gates.setdefault(g.run_id, {})[g.gate_name] = (
            g.direction.value if hasattr(g.direction, "value") else str(g.direction),
            g.confidence or 0.0,
        )

    # Build run_id → entry pnl + side
    run_outcome: dict[int, tuple[str, float]] = {}
    for e in entries:
        if e.analysis_run_id:
            run_outcome[e.analysis_run_id] = (e.side, e.pnl or 0.0)

    # Aggregate per gate
    gate_stats: dict[str, dict] = {}
    for run_id, (side, pnl) in run_outcome.items():
        gates = run_gates.get(run_id, {})
        # "correct" = gate direction matches trade side AND trade was profitable,
        # OR gate direction opposes trade side AND trade lost money
        profitable = pnl > 0
        for gate_name, (direction, confidence) in gates.items():
            if gate_name not in gate_stats:
                gate_stats[gate_name] = {
                    "total": 0, "correct": 0, "conf_sum": 0.0,
                    "pnl_correct": 0.0, "pnl_wrong": 0.0,
                }
            s = gate_stats[gate_name]
            s["total"] += 1
            s["conf_sum"] += confidence

            aligned = (direction.upper() == side.upper())
            correct = (aligned and profitable) or (not aligned and not profitable)
            if correct:
                s["correct"] += 1
                s["pnl_correct"] += pnl
            else:
                s["pnl_wrong"] += pnl

    gates_out = []
    for name, s in sorted(gate_stats.items(), key=lambda x: -x[1]["total"]):
        total = s["total"]
        gates_out.append(GateAttribution(
            gate_name=name,
            total_trades=total,
            correct_calls=s["correct"],
            accuracy_pct=round((s["correct"] / total) * 100, 1) if total else 0,
            avg_confidence=round(s["conf_sum"] / total, 3) if total else 0,
            pnl_when_correct=round(s["pnl_correct"], 4),
            pnl_when_wrong=round(s["pnl_wrong"], 4),
        ))

    return AttributionReport(
        total_closed_trades=len(entries),
        total_pnl=round(total_pnl, 4),
        gates=gates_out,
    )

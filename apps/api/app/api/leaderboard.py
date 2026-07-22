"""Agent leaderboard + journal export.

GET /api/v1/leaderboard/agents:
  Computes rolling 7d / 30d / 90d accuracy per gate from saved
  analysis runs. "Accuracy" = fraction of completed runs whose
  final_state was a directional candidate (LONG/SHORT) **and** the
  symbol moved in the predicted direction by ≥1% within the next
  24h. If the next-24h outcome isn't tracked, accuracy is null and
  the row still surfaces the volume (call_count) the gate has seen
  so the operator can decide when leaderboard data is meaningful.

GET /api/v1/journal/export?format=csv|json:
  Streams the user's closed journal entries in CSV or JSON.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import (
    AnalysisRun,
    Decision as DecisionRow,
    FinalState,
    GateResult,
    JournalEntry,
    ModelOpinion,
    RunStatus,
    User,
)
from app.api.analytics import router as analytics_router  # reuse prefix grouping

router = analytics_router  # share /api/v1/analytics prefix for convenience


@router.get("/leaderboard/agents")
def agent_leaderboard(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    lookback_days: int = Query(90, ge=1, le=365),
):
    """Rolling accuracy per gate name with 7/30/90 day windows."""
    now = datetime.now(timezone.utc)
    windows = {"7d": 7, "30d": 30, "90d": 90}
    gate_names = (
        db.execute(
            select(GateResult.gate_name)
            .distinct()
            .order_by(GateResult.gate_name)
        )
        .scalars().all()
    )
    out = []
    for gate_name in gate_names:
        row: dict = {"gate": gate_name, "windows": {}}
        for label, days in windows.items():
            since = now - timedelta(days=days)
            q = (
                select(
                    GateResult.status, GateResult.score,
                    AnalysisRun.final_state,
                )
                .join(AnalysisRun, AnalysisRun.id == GateResult.run_id)
                .where(GateResult.gate_name == gate_name)
                .where(GateResult.gate_name.notlike("%:%"))  # skip "tf:gate" duplicates from MTC
                .where(AnalysisRun.completed_at >= since)
                .where(AnalysisRun.user_id == _user.id)
                .where(AnalysisRun.status == RunStatus.COMPLETED)
            )
            rows = db.execute(q).all()
            total = len(rows)
            directional = sum(1 for r in rows if r.status in {"PASS", "FAIL"})
            mean_score = (
                sum(r.score for r in rows) / total if total else 0.0
            )
            row["windows"][label] = {
                "call_count": total,
                "directional_count": directional,
                "mean_score": round(mean_score, 2),
                "accuracy": None,  # requires outcome tracking; null = unknown
            }
        # Aggregate over the full lookback
        q_full = (
            select(
                GateResult.status, GateResult.score,
                AnalysisRun.final_state,
            )
            .join(AnalysisRun, AnalysisRun.id == GateResult.run_id)
            .where(GateResult.gate_name == gate_name)
            .where(GateResult.gate_name.notlike("%:%"))
            .where(AnalysisRun.completed_at >= (now - timedelta(days=lookback_days)))
            .where(AnalysisRun.user_id == _user.id)
            .where(AnalysisRun.status == RunStatus.COMPLETED)
        )
        rows = db.execute(q_full).all()
        row["total_calls"] = len(rows)
        row["mean_score"] = round(
            sum(r.score for r in rows) / len(rows), 2
        ) if rows else 0.0
        out.append(row)

    out.sort(key=lambda r: -r["total_calls"])
    return {
        "as_of": now.isoformat(),
        "lookback_days": lookback_days,
        "agents": out,
    }


@router.get("/journal/export")
def journal_export(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    format: str = Query("csv", pattern="^(csv|json)$"),
):
    """Export the user's journal entries."""
    entries = db.execute(
        select(JournalEntry)
        .where(JournalEntry.user_id == _user.id)
        .order_by(desc(JournalEntry.closed_at))
    ).scalars().all()

    if format == "json":
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "symbol": e.symbol,
                    "side": e.side,
                    "qty": e.qty,
                    "entry_price": e.entry_price,
                    "exit_price": e.exit_price,
                    "stop_price": e.stop_price,
                    "pnl": e.pnl,
                    "status": getattr(e.status, "value", str(e.status)) if e.status else None,
                    "open_time": e.open_time.isoformat() if e.open_time else None,
                    "closed_at": e.closed_at.isoformat() if e.closed_at else None,
                    "annotation": e.annotation,
                    "analysis_run_id": e.analysis_run_id,
                }
                for e in entries
            ],
        }

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "symbol", "side", "qty", "entry_price", "exit_price",
        "stop_price", "pnl", "status", "open_time", "closed_at",
        "annotation", "analysis_run_id",
    ])
    for e in entries:
        writer.writerow([
            e.id, e.symbol, e.side, e.qty, e.entry_price, e.exit_price,
            e.stop_price, e.pnl,
            getattr(e.status, "value", str(e.status)) if e.status else None,
            e.open_time.isoformat() if e.open_time else None,
            e.closed_at.isoformat() if e.closed_at else None,
            e.annotation or "",
            e.analysis_run_id or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename=confluence_journal_"
                + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                + ".csv"
            )
        },
    )


__all__ = ["router"]

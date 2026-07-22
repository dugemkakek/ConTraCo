"""Multi-Timeframe Confluence (MTC) API routes.

Provides endpoints that run the full gate pipeline across multiple
timeframes (e.g., 4H, 1H, 15m) and return a combined MTC alignment score.
"""


from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import User
from app.engine.mtf_runner import DEFAULT_MTF_TIMEFRAMES, run_mtc_analysis

router = APIRouter(prefix="/api/v1/mtf", tags=["mtf"])


class MTCRequest(BaseModel):
    symbol: str
    timeframes: list[str] | None = None
    strategy: str = "balanced"
    candle_limit: int = 300


class MTCBiasOut(BaseModel):
    htf_bias: float
    mtf_bias: float
    ltf_bias: float
    alignment: float
    mtc_score: float


class MTCRunOut(BaseModel):
    id: int
    symbol: str
    timeframes: str
    status: str
    final_state: str | None
    note: str | None
    mtc: MTCBiasOut | None
    decision: dict[str, Any] | None
    gates: list[dict[str, Any]]
    opinions: list[dict[str, Any]]


def _parse_mtc_note(note: str | None) -> MTCBiasOut | None:
    """Extract MTC bias values from the run note."""
    if not note or "MTF:" not in note:
        return None
    try:
        parts = note.split("Bias: ")[1]
        biases = {}
        for chunk in parts.split(" "):
            if "=" in chunk:
                k, v = chunk.split("=")
                biases[k] = float(v)
        # Extract alignment
        align_str = note.split("Alignment: ")[1].split(".")[0] if "Alignment: " in note else "0"
        alignment = float(align_str.replace("%", "")) / 100 if "%" in align_str else 0.0
        return MTCBiasOut(
            htf_bias=biases.get("HTF", 0.0),
            mtf_bias=biases.get("MTF", 0.0),
            ltf_bias=biases.get("LTF", 0.0),
            alignment=alignment,
            mtc_score=round(
                (biases.get("HTF", 0.0) * 0.5 +
                 biases.get("MTF", 0.0) * 0.3 +
                 biases.get("LTF", 0.0) * 0.2), 1
            ),
        )
    except Exception:
        return None


@router.post("/run", response_model=MTCRunOut)
async def mtf_run(
    body: MTCRequest,
    _user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Run multi-timeframe confluence analysis."""
    timeframes = body.timeframes or DEFAULT_MTF_TIMEFRAMES
    run = await run_mtc_analysis(
        db, user=_user, symbol=body.symbol,
        timeframes=timeframes, strategy_name=body.strategy,
        candle_limit=body.candle_limit,
    )

    return MTCRunOut(
        id=run.id,
        symbol=run.symbol,
        timeframes=run.timeframe,
        status=run.status.value,
        final_state=run.final_state.value if run.final_state else None,
        note=run.note,
        mtc=_parse_mtc_note(run.note),
        decision={
            "final_state": run.decision.final_state.value if run.decision else None,
            "composite_score": run.decision.composite_score if run.decision else 0.0,
            "reason": run.decision.reason if run.decision else "",
        } if run.decision else None,
        gates=[
            {"name": g.gate_name, "status": g.status.value if hasattr(g.status, "value") else str(g.status),
             "score": g.score, "reason": g.reason}
            for g in (run.gates or [])
        ],
        opinions=[
            {"role": o.role, "direction": o.direction.value if hasattr(o.direction, "value") else str(o.direction),
             "confidence": o.confidence, "reason": o.reason}
            for o in (run.opinions or [])
        ],
    )


@router.get("/presets")
def mtf_presets(_user: Annotated[User, Depends(get_current_user)]):
    """Return available MTC timeframe presets."""
    return {
        "presets": [
            {"name": "swing", "timeframes": ["1d", "4h", "1h"], "label": "Swing (1D/4H/1H)"},
            {"name": "intraday", "timeframes": ["4h", "1h", "15m"], "label": "Intraday (4H/1H/15m)"},
            {"name": "scalp", "timeframes": ["1h", "15m", "5m"], "label": "Scalp (1H/15M/5M)"},
        ],
        "default": DEFAULT_MTF_TIMEFRAMES,
    }
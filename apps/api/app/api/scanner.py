"""Multi-symbol scanner.

Runs analysis on a configured universe in the background, surfaces
the latest state per symbol, and emits Redis pub/sub messages for
notable results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.redis_client import get_redis
from app.db.models import (
    AnalysisRun,
    FinalState,
    User,
)
from app.engine.runner import run_analysis
from app.services.market_data.factory import build_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scanner", tags=["scanner"])

REDIS_SCAN_CHANNEL = "confluence:scan"

# Per-user scan state — keyed by user id; serializable so it survives restarts.
_scan_status: dict[int, dict] = {}


class ScanRequest(BaseModel):
    symbols: list[str] | None = None  # default: provider's supported universe
    timeframe: str = "1h"
    strategy: str = "balanced"
    candle_limit: int = 200


class ScanStatusOut(BaseModel):
    running: bool
    started_at: str | None
    completed: int
    total: int
    current: str | None
    notable: list[dict]


@router.get("/latest", response_model=list[dict])
def latest_results(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
):
    """Return the most recent run per symbol for the current user."""
    rows = db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.user_id == user.id)
        .order_by(desc(AnalysisRun.started_at))
        .limit(limit * 4)  # extra; dedup per symbol below
    ).scalars().all()
    seen: dict[str, AnalysisRun] = {}
    for r in rows:
        if r.symbol not in seen:
            seen[r.symbol] = r
        if len(seen) >= limit:
            break
    return [
        {
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "final_state": r.final_state.value if r.final_state else None,
            "run_id": r.id,
            "started_at": r.started_at.isoformat(),
        }
        for r in seen.values()
    ]


@router.post("/run", response_model=ScanStatusOut)
async def start_scan(
    body: ScanRequest,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    provider = build_provider()
    universe = body.symbols or provider.supported_symbols()
    universe = [s.upper() for s in universe if provider.is_symbol_supported(s.upper())]
    if not universe:
        raise HTTPException(status_code=400, detail="no symbols to scan")

    _scan_status[user.id] = {
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed": 0,
        "total": len(universe),
        "current": None,
        "notable": [],
    }
    background.add_task(_run_scan, user.id, universe, body.timeframe, body.strategy, body.candle_limit)
    return ScanStatusOut(**_scan_status[user.id])


@router.get("/status", response_model=ScanStatusOut)
def scan_status(user: Annotated[User, Depends(get_current_user)]):
    s = _scan_status.get(user.id)
    if s is None:
        return ScanStatusOut(running=False, started_at=None, completed=0, total=0, current=None, notable=[])
    return ScanStatusOut(**s)


async def _run_scan(
    user_id: int,
    universe: list[str],
    timeframe: str,
    strategy: str,
    candle_limit: int,
) -> None:
    """Background scan loop. One analysis at a time so we don't hammer the provider."""
    from app.db import SessionLocal  # local import: avoid circular

    redis = await get_redis()
    status = _scan_status.get(user_id, {})
    notable: list[dict] = status.get("notable", [])

    for symbol in universe:
        status["current"] = symbol
        _scan_status[user_id] = status
        SessionMaker = SessionLocal()
        db = SessionMaker()
        try:
            user = db.get(User, user_id)
            if user is None:
                return
            run = await run_analysis(
                db, user=user, symbol=symbol, timeframe=timeframe,
                strategy_name=strategy, candle_limit=candle_limit,
            )
            if run.final_state in (FinalState.LONG_CANDIDATE, FinalState.SHORT_CANDIDATE):
                notable.append({
                    "symbol": run.symbol,
                    "timeframe": run.timeframe,
                    "final_state": run.final_state.value,
                    "run_id": run.id,
                    "started_at": run.started_at.isoformat(),
                })
                if redis is not None:
                    try:
                        await redis.publish(
                            REDIS_SCAN_CHANNEL,
                            json.dumps({
                                "user_id": user_id,
                                "symbol": run.symbol,
                                "timeframe": run.timeframe,
                                "final_state": run.final_state.value,
                                "run_id": run.id,
                            }),
                        )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan failed for %s: %s", symbol, exc)
        finally:
            try:
                db.close()
            except Exception:  # noqa: BLE001
                pass
            status["completed"] += 1
            status["notable"] = notable[-50:]
            _scan_status[user_id] = status
        # Be polite: 250ms between symbols.
        await asyncio.sleep(0.25)

    status["running"] = False
    status["current"] = None
    _scan_status[user_id] = status


__all__ = ["router", "REDIS_SCAN_CHANNEL"]

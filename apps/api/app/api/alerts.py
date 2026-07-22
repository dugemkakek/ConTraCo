"""Alert management API routes."""


import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import Alert as AlertModel, AlertSeverity, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    symbol: str
    condition_type: str  # price_above, price_below, gate_score_above, indicator
    condition_params: dict
    severity: str = "INFO"
    message: str = ""


class AlertOut(BaseModel):
    id: int
    symbol: str
    condition_type: str
    condition_params: dict
    severity: str
    message: str
    is_read: bool
    created_at: str


@router.get("", response_model=list[AlertOut])
def list_alerts(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = False,
):
    stmt = select(AlertModel).order_by(desc(AlertModel.created_at)).limit(100)
    if unread_only:
        stmt = stmt.where(AlertModel.is_read == False)  # noqa: E712
    return [
        AlertOut(
            id=a.id, symbol=a.symbol,
            condition_type="", condition_params={},
            severity=a.severity.value, message=a.message,
            is_read=a.is_read,
            created_at=a.created_at.isoformat(),
        )
        for a in db.execute(stmt).scalars().all()
    ]


@router.post("", response_model=AlertOut)
def create_alert(
    body: AlertCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = AlertModel(
        user_id=user.id,
        symbol=body.symbol,
        severity=AlertSeverity(body.severity),
        message=body.message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return AlertOut(
        id=alert.id, symbol=alert.symbol,
        condition_type="", condition_params={},
        severity=alert.severity.value, message=alert.message,
        is_read=alert.is_read,
        created_at=alert.created_at.isoformat(),
    )


@router.put("/{alert_id}/read")
def mark_read(
    alert_id: int,
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = db.get(AlertModel, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.is_read = True
    db.commit()
    return {"ok": True}

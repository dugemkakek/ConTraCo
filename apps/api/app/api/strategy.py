"""Strategy config + presets API."""


from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.db.models import StrategyConfig, User
from app.engine.strategy import get_active_spec, load_preset, parse_spec, save_spec

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


class StrategyConfigOut(BaseModel):
    id: int
    name: str
    version: int
    is_active: bool
    payload: dict[str, Any]
    created_at: str


class SaveRequest(BaseModel):
    name: str = Field(default="balanced")
    payload: dict[str, Any]
    activate: bool = True


@router.get("/presets")
def list_presets():
    """Return the bundled presets (aggressive / balanced / conservative)."""
    return {
        "presets": [
            {"name": n, "payload": load_preset(n)} for n in ("aggressive", "balanced", "conservative")
        ]
    }


@router.get("/active", response_model=StrategyConfigOut)
def get_active(
    db: Annotated[Session, Depends(get_db)],
    name: str = "balanced",
):
    """Return the active strategy config for ``name``.

    On a fresh DB with no saved row, this still returns a usable
    payload by falling back to the bundled preset — same behavior as
    ``app.engine.strategy.get_active_spec``. This keeps the
    ``/settings`` page and the smoke test green from first boot.
    """
    config_id, spec = get_active_spec(db, name=name)
    if config_id:
        row = db.get(StrategyConfig, config_id)
        return StrategyConfigOut(
            id=row.id,
            name=row.name,
            version=row.version,
            is_active=row.is_active,
            payload=row.payload,
            created_at=row.created_at.isoformat(),
        )
    return StrategyConfigOut(
        id=0,
        name=name,
        version=0,
        is_active=False,
        payload=spec.model_dump(mode="json"),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("", response_model=list[StrategyConfigOut])
def list_configs(
    db: Annotated[Session, Depends(get_db)],
    name: str | None = None,
    limit: int = 50,
):
    stmt = select(StrategyConfig).order_by(desc(StrategyConfig.created_at)).limit(limit)
    if name:
        stmt = stmt.where(StrategyConfig.name == name)
    rows = db.execute(stmt).scalars().all()
    return [
        StrategyConfigOut(
            id=r.id, name=r.name, version=r.version, is_active=r.is_active,
            payload=r.payload, created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("", response_model=StrategyConfigOut)
def save_config(
    body: SaveRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        parse_spec({**body.payload, "name": body.name})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid spec: {exc}")
    new_id = save_spec(
        db, name=body.name, payload=body.payload,
        created_by_id=user.id, activate=body.activate,
    )
    row = db.get(StrategyConfig, new_id)
    return StrategyConfigOut(
        id=row.id, name=row.name, version=row.version, is_active=row.is_active,
        payload=row.payload, created_at=row.created_at.isoformat(),
    )


@router.post("/seed-defaults")
def seed_defaults(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Create a v1 of each preset as an active config so the strategy
    settings page has rows to show on a fresh install."""
    out: list[int] = []
    for name in ("aggressive", "balanced", "conservative"):
        existing = db.execute(
            select(StrategyConfig)
            .where(StrategyConfig.name == name)
            .order_by(desc(StrategyConfig.version))
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        out.append(save_spec(db, name=name, payload=load_preset(name), created_by_id=user.id))
    return {"seeded": out}


__all__ = ["router"]
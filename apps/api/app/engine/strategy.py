"""Strategy config schema, defaults, and presets.

The default block in this module is the verbatim reference from
``claude reccomendation.txt`` section 12. Editing that block is a
contract change — if you change a key you must also add a migration
to ``alembic/versions``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GateWeight(BaseModel):
    market_regime: float
    classical_ta: float
    market_structure: float
    volume_momentum: float
    fundamental_context: float
    risk_tradeability: float

    @model_validator(mode="after")
    def _sums_to_one(self) -> "GateWeight":
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"gate weights must sum to 1.0, got {total}")
        return self


class RoleSpec(BaseModel):
    weight: float = Field(ge=0, le=1)
    confidence_cap: float = Field(ge=0, le=1, default=1.0)


class NonDirectionalRole(BaseModel):
    runs_after_decision: bool = True


class StrategyConfigSpec(BaseModel):
    name: str = "balanced"
    minimum_data_quality: float = Field(ge=0, le=1, default=0.95)
    minimum_quorum_gate_count: int = Field(ge=1, default=4)
    minimum_direction_score: float = Field(ge=0, le=100, default=55)
    minimum_model_agreement: float = Field(ge=0, le=1, default=0.6)
    minimum_risk_reward: float = Field(gt=0, default=2.0)
    maximum_stop_atr_multiple: float = Field(gt=0, default=3.5)
    maximum_conflicting_model_confidence: float = Field(ge=0, le=1, default=0.7)
    composite_gate_weight: float = Field(ge=0, le=1, default=0.55)
    composite_model_weight: float = Field(ge=0, le=1, default=0.45)
    gates: GateWeight
    directional_roles: dict[Literal[
        "technical_analyst", "market_context_analyst",
        "risk_reviewer", "skeptical_reviewer",
    ], RoleSpec]
    non_directional_roles: dict[Literal["trade_planner", "synthesis_reviewer"], NonDirectionalRole] = (
        NonDirectionalRole(runs_after_decision=True),
    )  # type: ignore[assignment]
    hard_veto_risk_flags: list[str] = Field(
        default_factory=lambda: ["data_integrity", "liquidity_trap", "manipulation_suspected"]
    )

    @model_validator(mode="after")
    def _composite_sums_to_one(self) -> "StrategyConfigSpec":
        if abs(self.composite_gate_weight + self.composite_model_weight - 1.0) > 1e-6:
            raise ValueError(
                "composite_gate_weight + composite_model_weight must equal 1.0"
            )
        total = sum(r.weight for r in self.directional_roles.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"directional role weights must sum to 1.0, got {total}")
        return self

    @field_validator("directional_roles")
    @classmethod
    def _all_roles_present(cls, v):
        required = {"technical_analyst", "market_context_analyst", "risk_reviewer", "skeptical_reviewer"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"missing directional roles: {missing}")
        return v


# Default config — the verbatim block from the spec.
DEFAULT_CONFIG: dict[str, Any] = {
    "minimum_data_quality": 0.95,
    "minimum_quorum_gate_count": 4,
    "minimum_direction_score": 55,
    "minimum_model_agreement": 0.60,
    "minimum_risk_reward": 2.0,
    "maximum_stop_atr_multiple": 3.5,
    "composite_gate_weight": 0.55,
    "composite_model_weight": 0.45,
    "gates": {
        "market_regime": 0.18,
        "classical_ta": 0.20,
        "market_structure": 0.20,
        "volume_momentum": 0.14,
        "fundamental_context": 0.13,
        "risk_tradeability": 0.15,
    },
    "directional_roles": {
        "technical_analyst":      {"weight": 0.34, "confidence_cap": 1.00},
        "market_context_analyst": {"weight": 0.22, "confidence_cap": 1.00},
        "risk_reviewer":          {"weight": 0.24, "confidence_cap": 0.35},
        "skeptical_reviewer":     {"weight": 0.20, "confidence_cap": 0.35},
    },
    "non_directional_roles": {
        "trade_planner": {"runs_after_decision": True},
        "synthesis_reviewer": {"runs_after_decision": True},
    },
    "hard_veto_risk_flags": [
        "data_integrity",
        "liquidity_trap",
        "manipulation_suspected",
    ],
}

# Preset overrides (Aggressive / Balanced / Conservative). The balanced
# preset mirrors the default config; the other two tweak the score
# thresholds to be more or less selective.
PRESET_OVERRIDES: dict[str, dict[str, Any]] = {
    "aggressive": {
        "minimum_direction_score": 45,
        "minimum_model_agreement": 0.5,
        "minimum_risk_reward": 1.5,
    },
    "balanced": {},
    "conservative": {
        "minimum_direction_score": 65,
        "minimum_model_agreement": 0.7,
        "minimum_risk_reward": 2.5,
    },
}

PRESETS_DIR = Path(__file__).resolve().parents[3] / "packages" / "strategy-presets"


def load_preset(name: str) -> dict[str, Any]:
    """Merge a preset file (if present) on top of DEFAULT_CONFIG.

    Preset JSONs in ``packages/strategy-presets`` may contain only the
    keys they want to override; everything else falls back to the spec
    defaults so they cannot drift.
    """
    if name not in PRESET_OVERRIDES:
        raise ValueError(f"unknown preset {name!r}; valid: {list(PRESET_OVERRIDES)}")
    payload = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    payload["name"] = name
    # Round-trip through the spec so callers always see a fully
    # populated payload (including derived defaults like
    # ``non_directional_roles``), not just the keys we happened to
    # write into ``DEFAULT_CONFIG``.
    spec = parse_spec(payload)
    payload = spec.model_dump(mode="json")
    preset_file = PRESETS_DIR / f"{name}.json"
    if preset_file.exists():
        try:
            file_payload = json.loads(preset_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            file_payload = {}
        # Only allow scalar override keys; never replace sub-dicts wholesale
        # to keep presets safely partial.
        for k, v in file_payload.items():
            if k in {"minimum_direction_score", "minimum_model_agreement", "minimum_risk_reward"}:
                payload[k] = v
    # apply built-in override too
    for k, v in PRESET_OVERRIDES[name].items():
        payload[k] = v
    return payload


def parse_spec(payload: dict[str, Any]) -> StrategyConfigSpec:
    return StrategyConfigSpec.model_validate(payload)


def get_active_spec(db, *, name: str = "balanced") -> tuple[int, StrategyConfigSpec]:
    """Fetch the latest version of the named config; fall back to in-memory default.

    Returns ``(config_id, spec)``. If no config row exists, returns
    ``(0, spec_from_defaults)`` so the rest of the engine can run.
    """
    from app.db.models import StrategyConfig
    from sqlalchemy import select, desc  # noqa: PLC0415

    row = db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.name == name)
        .order_by(desc(StrategyConfig.version))
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return 0, parse_spec(load_preset(name))
    return row.id, parse_spec(row.payload)


def save_spec(
    db,
    *,
    name: str,
    payload: dict[str, Any],
    created_by_id: int | None = None,
    activate: bool = True,
) -> int:
    """Insert a new version of a strategy config.

    Bumps ``version`` monotonically per ``name``. If ``activate``, the
    previously-active version of the same name is deactivated.
    """
    from app.db.models import StrategyConfig
    from sqlalchemy import select, desc, update  # noqa: PLC0415

    # Validate first; let pydantic surface the error.
    spec = parse_spec({**payload, "name": name})

    last = db.execute(
        select(StrategyConfig)
        .where(StrategyConfig.name == name)
        .order_by(desc(StrategyConfig.version))
        .limit(1)
    ).scalar_one_or_none()
    new_version = (last.version + 1) if last else 1
    if activate:
        db.execute(
            update(StrategyConfig)
            .where(StrategyConfig.name == name)
            .values(is_active=False)
        )
    row = StrategyConfig(
        name=name,
        version=new_version,
        payload=spec.model_dump(mode="json"),
        is_active=activate,
        created_by_id=created_by_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


__all__ = [
    "DEFAULT_CONFIG",
    "PRESET_OVERRIDES",
    "PRESETS_DIR",
    "RoleSpec",
    "GateWeight",
    "NonDirectionalRole",
    "StrategyConfigSpec",
    "get_active_spec",
    "load_preset",
    "parse_spec",
    "save_spec",
]

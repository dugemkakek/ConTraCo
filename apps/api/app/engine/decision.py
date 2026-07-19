"""Deterministic 7-stage decision engine.

Implements the pipeline from ``claude reccomendation.txt`` section 12
verbatim. The function ``decide()`` is pure: given a list of
``GateEvaluation`` and ``ModelOpinionData`` objects plus a
``StrategyConfigSpec``, it returns a ``DecisionResult``. No I/O.

The orchestrator (``app.engine.runner``) is the I/O wrapper that
fetches candles, runs gates, calls the AI council, calls ``decide()``,
and persists everything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from app.db.models import Direction, FinalState, GateStatus, ModelStatus
from app.engine.gates import GateEvaluation
from app.engine.strategy import StrategyConfigSpec

logger = logging.getLogger(__name__)


class ModelOpinionLike(Protocol):
    """Duck-typed view of a council opinion.

    ``is_valid`` is treated by the decision engine as either a ``bool``
    attribute or a zero-arg callable (see ``_is_valid_opinion``) so the
    same protocol accepts the council dataclass (where it is a
    ``@property``) and the test fakes (where it is a method).
    """

    role: str
    status: ModelStatus
    direction: Direction
    confidence: float
    role_weight: float
    confidence_cap: float
    risk_flags: list[str]
    evidence_ids: list[str]
    is_valid: object  # bool | () -> bool


@dataclass
class DecisionResult:
    final_state: FinalState
    gate_score: float
    model_score: float
    composite_score: float
    model_agreement: float
    data_completeness: float
    model_completeness: float
    vetoes: list[str] = field(default_factory=list)
    veto_sources: list[str] = field(default_factory=list)
    reason: str = ""

    def to_db(self) -> dict:
        return {
            "final_state": self.final_state,
            "gate_score": self.gate_score,
            "model_score": self.model_score,
            "composite_score": self.composite_score,
            "model_agreement": self.model_agreement,
            "data_completeness": self.data_completeness,
            "model_completeness": self.model_completeness,
            "vetoes": self.vetoes,
            "veto_sources": self.veto_sources,
            "reason": self.reason,
        }


def _gate_score(
    gates: Iterable[GateEvaluation], spec: StrategyConfigSpec
) -> tuple[float, int, int]:
    """Step 1.

    Returns (gate_score, quorum_count, available_count). UNAVAILABLE
    gates are excluded from both the numerator and the weight sum
    (renormalization, not zero-fill). Gate F (``risk_tradeability``)
    contributes to quorum whenever it produced any status, including
    VETO, per the spec.
    """
    contributions: list[tuple[float, float, float]] = []
    quorum_count = 0
    for g in gates:
        if g.status == GateStatus.UNAVAILABLE:
            continue
        w = spec.gates.model_dump().get(g.name, 0.0)
        if w == 0.0:
            continue
        contributions.append((g.score, w, g.confidence))
        quorum_count += 1
    if not contributions:
        return 0.0, 0, 0
    num = sum(s * w * c for s, w, c in contributions)
    den = sum(w for _, w, _ in contributions)
    if den == 0:
        return 0.0, 0, 0
    # The spec text says "100 * (...)" but explicitly requires the
    # result to be in [-100, 100]; since `gate_score` is already on
    # that scale, the *100 is a typo in the spec. The math here
    # produces the documented range.
    return (num / den), quorum_count, len(contributions)


def _is_valid_opinion(o) -> bool:
    """``is_valid`` may be a bool property or a callable — handle both."""
    v = getattr(o, "is_valid", None)
    if v is None:
        return False
    return bool(v() if callable(v) else v)


def _model_score(
    opinions: Iterable[ModelOpinionLike], spec: StrategyConfigSpec
) -> tuple[float, float, int]:
    """Steps 2 + 3.

    Returns (model_score, agreement, valid_count). Only roles present
    in ``directional_roles`` participate — non-directional roles
    (``trade_planner``, ``synthesis_reviewer``) run after the decision.
    """
    directional = set(spec.directional_roles.keys())
    valid = [o for o in opinions if _is_valid_opinion(o) and o.role in directional]
    if not valid:
        return 0.0, 0.0, 0

    contributions: list[tuple[float, float, float]] = []
    for o in valid:
        sign = {"LONG": 1.0, "SHORT": -1.0}.get(o.direction.value, 0.0)
        cap = spec.directional_roles[o.role].confidence_cap
        # Confidence cap: only applies to positive-contribution direction.
        # A skeptic flagging SHORT is not capped (they can pull down).
        eff_conf = (
            min(o.confidence, cap) if sign > 0
            else min(o.confidence, 1.0)
        )
        weight = spec.directional_roles[o.role].weight
        contributions.append((sign, weight, eff_conf))

    num = sum(s * w * c for s, w, c in contributions)
    den = sum(w for _, w, _ in contributions)
    # Model score is in [-100, 100]: contributions have magnitude
    # at most |sign|=1 * weight<=1 * conf<=1, so the ratio is in [-1, 1]
    # and we rescale by 100 to land in the documented range.
    score = (num / den) * 100.0 if den else 0.0

    # Step 3 — weighted agreement on the majority direction.
    majority_sign = 1.0 if score > 0 else -1.0 if score < 0 else 0.0
    if majority_sign == 0:
        return score, 0.0, len(valid)
    total_w = 0.0
    agree_w = 0.0
    for o in valid:
        w = spec.directional_roles[o.role].weight
        total_w += w
        sign = {"LONG": 1.0, "SHORT": -1.0}.get(o.direction.value, 0.0)
        if sign == majority_sign:
            agree_w += w
    agreement = agree_w / total_w if total_w else 0.0
    return score, agreement, len(valid)


def decide(
    gates: list[GateEvaluation],
    opinions: list[ModelOpinionLike],
    spec: StrategyConfigSpec,
    total_configured_gates: int = 6,
    total_directional_roles: int = 4,
) -> DecisionResult:
    """Run the full 7-stage pipeline. Pure function."""
    vetoes: list[str] = []
    veto_sources: list[str] = []

    # Step 1: gate score
    gate_s, quorum_count, _ = _gate_score(gates, spec)

    # Step 5: completeness + quorum
    data_completeness = quorum_count / total_configured_gates if total_configured_gates else 0.0

    if quorum_count < spec.minimum_quorum_gate_count:
        return DecisionResult(
            final_state=FinalState.WAIT,
            gate_score=gate_s,
            model_score=0.0,
            composite_score=0.0,
            model_agreement=0.0,
            data_completeness=data_completeness,
            model_completeness=0.0,
            vetoes=["INSUFFICIENT_QUORUM"],
            veto_sources=["quorum"],
            reason=(
                f"quorum unmet: {quorum_count} gates with status, "
                f"need {spec.minimum_quorum_gate_count}"
            ),
        )

    # Step 2 + 3: model score and agreement
    model_s, agreement, valid_roles = _model_score(opinions, spec)
    model_completeness = (
        valid_roles / total_directional_roles if total_directional_roles else 0.0
    )

    # Step 4: composite
    composite = (
        gate_s * spec.composite_gate_weight
        + model_s * spec.composite_model_weight
    )

    # Step 6: vetoes and caps (in priority order)
    for g in gates:
        if g.status == GateStatus.VETO:
            vetoes.append(f"gate_veto:{g.name}:{g.reason}")
            veto_sources.append(f"gate:{g.name}")
    for o in opinions:
        if o.role not in set(spec.directional_roles.keys()):
            continue
        if not _is_valid_opinion(o):
            continue
        for flag in o.risk_flags:
            if flag in spec.hard_veto_risk_flags:
                vetoes.append(f"ai_veto:{o.role}:{flag}")
                veto_sources.append(f"role:{o.role}")
    if agreement < spec.minimum_model_agreement:
        vetoes.append(
            f"model_agreement:{agreement:.2f}<{spec.minimum_model_agreement:.2f}"
        )
        veto_sources.append("agreement")
    if data_completeness < spec.minimum_data_quality:
        vetoes.append(
            f"data_quality:{data_completeness:.2f}<{spec.minimum_data_quality:.2f}"
        )
        veto_sources.append("data")

    if vetoes:
        return DecisionResult(
            final_state=FinalState.AVOID,
            gate_score=gate_s,
            model_score=model_s,
            composite_score=composite,
            model_agreement=agreement,
            data_completeness=data_completeness,
            model_completeness=model_completeness,
            vetoes=vetoes,
            veto_sources=veto_sources,
            reason="veto(s) active: " + "; ".join(vetoes),
        )

    # Step 7: final state
    if abs(composite) < spec.minimum_direction_score:
        return DecisionResult(
            final_state=FinalState.WAIT,
            gate_score=gate_s,
            model_score=model_s,
            composite_score=composite,
            model_agreement=agreement,
            data_completeness=data_completeness,
            model_completeness=model_completeness,
            reason=(
                f"composite {composite:+.1f} below threshold "
                f"±{spec.minimum_direction_score:.0f}"
            ),
        )
    if composite >= spec.minimum_direction_score:
        return DecisionResult(
            final_state=FinalState.LONG_CANDIDATE,
            gate_score=gate_s,
            model_score=model_s,
            composite_score=composite,
            model_agreement=agreement,
            data_completeness=data_completeness,
            model_completeness=model_completeness,
            reason=f"long: composite {composite:+.1f} ≥ {spec.minimum_direction_score:.0f}",
        )
    return DecisionResult(
        final_state=FinalState.SHORT_CANDIDATE,
        gate_score=gate_s,
        model_score=model_s,
        composite_score=composite,
        model_agreement=agreement,
        data_completeness=data_completeness,
        model_completeness=model_completeness,
        reason=f"short: composite {composite:+.1f} ≤ -{spec.minimum_direction_score:.0f}",
    )


__all__ = ["DecisionResult", "ModelOpinionLike", "decide"]

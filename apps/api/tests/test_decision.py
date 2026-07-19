"""Unit tests for the decision engine — Step 1-7 of the spec."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.db.models import Direction, FinalState, GateStatus, ModelStatus
from app.engine.decision import DecisionResult, decide
from app.engine.gates import GateEvaluation
from app.engine.strategy import parse_spec, load_preset


@dataclass
class _Opinion:
    role: str
    status: ModelStatus
    direction: Direction
    confidence: float
    role_weight: float = 0.25
    confidence_cap: float = 1.0
    risk_flags: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.status == ModelStatus.VALID


def _spec():
    return parse_spec(load_preset("balanced"))


def _gate(name: str, score: float, status=GateStatus.PASS, confidence: float = 0.7):
    return GateEvaluation(
        name=name, status=status, score=score, confidence=confidence, reason="test"
    )


def _opinion(role: str, direction: Direction, confidence: float = 0.7, flags=None):
    return _Opinion(
        role=role, status=ModelStatus.VALID, direction=direction,
        confidence=confidence, risk_flags=flags or [],
    )


def test_unavailable_gates_excluded_from_score_but_quorum_fails():
    spec = _spec()
    gates = [_gate("classical_ta", 50.0)]
    result = decide(gates, [], spec)
    assert result.final_state == FinalState.WAIT
    assert "INSUFFICIENT_QUORUM" in result.vetoes


def test_bullish_run_passes_through_to_long_candidate():
    spec = _spec()
    gates = [
        _gate("market_regime", 100.0, confidence=1.0),
        _gate("classical_ta", 100.0, confidence=1.0),
        _gate("market_structure", 100.0, confidence=1.0),
        _gate("volume_momentum", 100.0, confidence=1.0),
        _gate("fundamental_context", 100.0, status=GateStatus.PASS, confidence=1.0),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 1.0),
        _opinion("market_context_analyst", Direction.LONG, 1.0),
        _opinion("risk_reviewer", Direction.LONG, 0.35),
        _opinion("skeptical_reviewer", Direction.LONG, 0.35),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.LONG_CANDIDATE
    assert result.composite_score > 0
    assert result.model_agreement > 0.5


def test_gate_veto_forces_avoid():
    spec = _spec()
    gates = [
        _gate("market_regime", 80.0),
        _gate("classical_ta", 70.0),
        _gate("market_structure", 60.0),
        _gate("volume_momentum", 65.0),
        _gate("fundamental_context", 30.0, status=GateStatus.NEUTRAL),
        GateEvaluation(
            name="risk_tradeability", status=GateStatus.VETO,
            score=0.0, confidence=1.0, reason="low liquidity",
        ),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 0.8),
        _opinion("market_context_analyst", Direction.LONG, 0.7),
        _opinion("risk_reviewer", Direction.LONG, 0.5),
        _opinion("skeptical_reviewer", Direction.LONG, 0.4),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.AVOID
    assert any("risk_tradeability" in v for v in result.vetoes)


def test_ai_risk_flag_triggers_avoid():
    spec = _spec()
    gates = [
        _gate("market_regime", 80.0),
        _gate("classical_ta", 70.0),
        _gate("market_structure", 60.0),
        _gate("volume_momentum", 65.0),
        _gate("fundamental_context", 30.0, status=GateStatus.NEUTRAL),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 0.8),
        _opinion("market_context_analyst", Direction.LONG, 0.7),
        _opinion("risk_reviewer", Direction.LONG, 0.5),
        _opinion("skeptical_reviewer", Direction.LONG, 0.4, flags=["liquidity_trap"]),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.AVOID
    assert any("ai_veto" in v for v in result.vetoes)


def test_skeptic_cap_does_not_silence_bearish_signal():
    spec = _spec()
    gates = [
        _gate("market_regime", 0.0, status=GateStatus.NEUTRAL),
        _gate("classical_ta", 0.0, status=GateStatus.NEUTRAL),
        _gate("market_structure", 0.0, status=GateStatus.NEUTRAL),
        _gate("volume_momentum", 0.0, status=GateStatus.NEUTRAL),
        _gate("fundamental_context", 0.0, status=GateStatus.NEUTRAL),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 0.4),
        _opinion("market_context_analyst", Direction.LONG, 0.4),
        _opinion("risk_reviewer", Direction.SHORT, 1.0),
        _opinion("skeptical_reviewer", Direction.SHORT, 1.0),
    ]
    result = decide(gates, opinions, spec)
    assert result.composite_score < 0
    assert result.model_agreement < 0.6


def test_composite_below_threshold_is_wait():
    spec = _spec()
    gates = [
        _gate("market_regime", 10.0),
        _gate("classical_ta", 10.0),
        _gate("market_structure", 10.0),
        _gate("volume_momentum", 10.0),
        _gate("fundamental_context", 0.0, status=GateStatus.NEUTRAL),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 0.4),
        _opinion("market_context_analyst", Direction.LONG, 0.4),
        _opinion("risk_reviewer", Direction.LONG, 0.3),
        _opinion("skeptical_reviewer", Direction.LONG, 0.3),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.WAIT
    assert "composite" in result.reason.lower() or "threshold" in result.reason.lower()


def test_low_agreement_forces_avoid():
    spec = _spec()
    gates = [
        _gate("market_regime", 80.0),
        _gate("classical_ta", 70.0),
        _gate("market_structure", 60.0),
        _gate("volume_momentum", 65.0),
        _gate("fundamental_context", 30.0, status=GateStatus.NEUTRAL),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.LONG, 0.8),
        _opinion("market_context_analyst", Direction.LONG, 0.8),
        _opinion("risk_reviewer", Direction.SHORT, 0.8),
        _opinion("skeptical_reviewer", Direction.SHORT, 0.8),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.AVOID
    assert any("model_agreement" in v for v in result.vetoes)


def test_short_candidate_when_bearish():
    spec = _spec()
    gates = [
        _gate("market_regime", -100.0, confidence=1.0),
        _gate("classical_ta", -100.0, confidence=1.0),
        _gate("market_structure", -100.0, confidence=1.0),
        _gate("volume_momentum", -100.0, confidence=1.0),
        _gate("fundamental_context", -100.0, status=GateStatus.FAIL, confidence=1.0),
        _gate("risk_tradeability", 0.0, status=GateStatus.PASS, confidence=1.0),
    ]
    opinions = [
        _opinion("technical_analyst", Direction.SHORT, 1.0),
        _opinion("market_context_analyst", Direction.SHORT, 1.0),
        _opinion("risk_reviewer", Direction.SHORT, 1.0),
        _opinion("skeptical_reviewer", Direction.SHORT, 1.0),
    ]
    result = decide(gates, opinions, spec)
    assert result.final_state == FinalState.SHORT_CANDIDATE
    assert result.composite_score < 0

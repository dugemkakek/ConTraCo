"""Tests for the LLM-backed council (Phase 7 brain).

These tests don't talk to a real LLM. They pin down three contracts:

1. With no ``LLM_API_KEY`` configured, the council still produces 6
   opinions and tags every one with ``provider_used == "ocg-stub"``.
2. The council adapter ALWAYS applies the role's ``role_weight`` and
   ``confidence_cap`` from the strategy spec, never whatever the model
   returns — so a chatty model can't bypass the skeptic/risk cap.
3. If the underlying client raises (transport error, malformed JSON),
   each role adapter returns a sentinel ``MISSING`` opinion so the
   decision engine still terminates and the run is persisted.
"""

from __future__ import annotations

import asyncio

import pytest

from app.db.models import Direction, GateStatus, ModelStatus
from app.engine.council import (
    ALL_ROLES,
    CouncilContext,
    ROLE_SPEC_DEFAULTS,
    get_client,
    run_council,
    set_client,
)
from app.engine.gates import GateEvaluation
from app.services.llm import LLMClient, LLMError, OpenAICompatClient, StubClient, build_client


def _ctx(scores: list[float] | None = None) -> CouncilContext:
    if scores is None:
        scores = [40.0, 20.0, 15.0, 10.0, 5.0, 0.0]
    return CouncilContext(
        symbol="BTC/USDT",
        timeframe="1h",
        candles=[],
        gates=[
            GateEvaluation(
                name=n,
                status=GateStatus.PASS,
                score=s,
                confidence=0.7,
                reason=f"{n} ok",
                evidence={},
            )
            for n, s in zip(
                [
                    "market_regime",
                    "classical_ta",
                    "market_structure",
                    "volume_momentum",
                    "fundamental_context",
                    "risk_tradeability",
                ],
                scores,
                strict=False,
            )
        ],
    )


@pytest.mark.asyncio
async def test_council_uses_stub_when_no_api_key():
    """No LLM_API_KEY -> StubClient -> every opinion tagged ocg-stub."""
    set_client(None)  # force a re-build from env
    # Ensure no key is in scope for this test.
    import os
    saved = {}
    for k in ("LLM_API_KEY", "INFERHUB_API_KEY", "INFERHUB_KEY"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        client = build_client()
        assert isinstance(client, StubClient), (
            f"expected StubClient, got {type(client).__name__}"
        )
        assert client.name == "ocg-stub"
        assert client.model == "ocg/minimax-m3"

        opinions = await run_council(_ctx())
        assert len(opinions) == 6
        for o in opinions:
            assert o.provider_used == "ocg-stub", o.role
            assert o.llm_model == "ocg/minimax-m3", o.role
            assert o.status in (ModelStatus.VALID, ModelStatus.MISSING), o.role
    finally:
        for k, v in saved.items():
            os.environ[k] = v


@pytest.mark.asyncio
async def test_council_enforces_role_weights_and_caps():
    """The spec-defined role_weight/confidence_cap win over model output."""

    class _ForceHighClient:
        name = "ocg"
        model = "ocg/minimax-m3"

        async def chat_json(self, system: str, user: str) -> dict:
            # Pretend the model is trying to give risk_reviewer 0.99
            # confidence and the skeptic 0.99 too — caps must clamp them.
            return {
                "status": "VALID",
                "direction": "LONG",
                "confidence": 0.99,
                "risk_flags": ["data_integrity"],
                "evidence_ids": ["market_regime"],
                "reason": "I am very confident (and trying to bypass the cap).",
            }

    set_client(_ForceHighClient())
    try:
        opinions = await run_council(_ctx())
        by_role = {o.role: o for o in opinions}
        # Risk + skeptic must stay <= 0.35 regardless of model output.
        for r in ("risk_reviewer", "skeptical_reviewer"):
            assert by_role[r].confidence <= ROLE_SPEC_DEFAULTS[r][1] + 1e-9, r
            assert by_role[r].role_weight == ROLE_SPEC_DEFAULTS[r][0], r
            assert by_role[r].confidence_cap == ROLE_SPEC_DEFAULTS[r][1], r
        # The other directional roles can go higher.
        for r in ("technical_analyst", "market_context_analyst"):
            assert by_role[r].role_weight == ROLE_SPEC_DEFAULTS[r][0], r
            assert by_role[r].confidence_cap == ROLE_SPEC_DEFAULTS[r][1], r
        # Risk flag still gets through (cap doesn't strip it).
        assert "data_integrity" in by_role["risk_reviewer"].risk_flags
    finally:
        set_client(None)


@pytest.mark.asyncio
async def test_council_survives_garbage_llm_response():
    """A client that always raises must not break the run."""

    class _BrokenClient:
        name = "ocg"
        model = "ocg/minimax-m3"

        async def chat_json(self, system: str, user: str) -> dict:
            raise LLMError("simulated 502 from upstream")

    set_client(_BrokenClient())
    try:
        opinions = await run_council(_ctx())
        assert len(opinions) == 6, f"expected 6 opinions, got {len(opinions)}"
        # All 4 directional roles fall back to MISSING so the decision
        # engine treats them as abstentions; planner + synthesis are
        # still VALID because they short-circuit.
        by_role = {o.role: o for o in opinions}
        for r in ("technical_analyst", "market_context_analyst",
                  "risk_reviewer", "skeptical_reviewer"):
            assert by_role[r].status == ModelStatus.MISSING, r
            assert by_role[r].direction == Direction.WAIT, r
            assert "llm_error" in by_role[r].reason, r
            assert by_role[r].provider_used == "ocg", r
        for r in ("trade_planner", "synthesis_reviewer"):
            assert by_role[r].status == ModelStatus.VALID, r
            assert by_role[r].provider_used == "ocg", r
    finally:
        set_client(None)


@pytest.mark.asyncio
async def test_invalid_status_with_risk_flags_is_preserved_as_valid_abstain(monkeypatch):
    """The risk_reviewer uses ``status=INVALID`` + ``risk_flags=[...]``
    to mean "I am flagging risk and abstaining on direction". A bare
    INVALID with no flags IS a true abstention and stays MISSING. The
    council must not collapse the former into MISSING because that
    silently drops the veto signal the decision engine needs.
    """

    class _RiskClient:
        name = "ocg"
        model = "ocg/minimax-m3"

        async def chat_json(self, system: str, user: str) -> dict:
            return {
                "status": "VETO",
                "direction": "WAIT",
                "confidence": 0.35,
                "risk_flags": ["data_integrity", "liquidity_trap"],
                "evidence_ids": ["market_regime"],
                "reason": "flagging regime + structure conflict",
            }

    set_client(_RiskClient())
    try:
        from app.engine.council import run_council
        opinions = await run_council(_ctx())
        by_role = {o.role: o for o in opinions}
        risk = by_role["risk_reviewer"]
        assert risk.status is ModelStatus.VALID, "veto with flags must stay VALID"
        assert risk.direction is Direction.WAIT
        assert risk.confidence == 0.0, "abstain-on-direction must be zeroed"
        assert "data_integrity" in risk.risk_flags
        assert "liquidity_trap" in risk.risk_flags
    finally:
        set_client(None)


@pytest.mark.asyncio
async def test_invalid_status_without_risk_flags_still_collapses_to_missing(monkeypatch):
    """Sanity: a bare INVALID with no risk_flags IS a true abstention
    and should collapse to MISSING as before. The fix above is
    specifically about the veto-with-flags case."""

    class _AbstainingClient:
        name = "ocg"
        model = "ocg/minimax-m3"

        async def chat_json(self, system: str, user: str) -> dict:
            return {
                "status": "FAIL",
                "direction": "WAIT",
                "confidence": 0.0,
                "risk_flags": [],
                "evidence_ids": [],
                "reason": "no opinion",
            }

    set_client(_AbstainingClient())
    try:
        from app.engine.council import run_council
        opinions = await run_council(_ctx())
        by_role = {o.role: o for o in opinions}
        # All 4 directional roles should collapse to MISSING.
        for r in ("technical_analyst", "market_context_analyst",
                  "risk_reviewer", "skeptical_reviewer"):
            assert by_role[r].status is ModelStatus.MISSING, r
    finally:
        set_client(None)


def test_set_client_round_trip():
    """``set_client`` overrides the cached client and ``get_client``
    returns the same instance afterwards."""
    sentinel = object()

    class _Sentinel(LLMClient):  # type: ignore[misc]
        # Minimal duck-typed client.
        name = "sentinel"
        model = "sentinel/model"

        async def chat_json(self, system: str, user: str) -> dict:
            return {}

    set_client(_Sentinel())  # type: ignore[arg-type]
    try:
        assert get_client().name == "sentinel"
    finally:
        set_client(None)
        assert get_client().name in {"ocg", "ocg-stub"}


def test_build_client_picks_openai_when_key_is_set():
    """When any of LLM_API_KEY / INFERHUB_API_KEY / INFERHUB_KEY is
    set, the factory returns the real OpenAICompatClient pointed at
    InferHub with the right model — no network call."""
    import os

    saved = {}
    for k in ("LLM_API_KEY", "INFERHUB_API_KEY", "INFERHUB_KEY"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        os.environ["INFERHUB_KEY"] = "sk-airo-test-key"
        client = build_client()
        assert isinstance(client, OpenAICompatClient), type(client).__name__
        assert client.name == "ocg"
        assert client.model == "ocg/minimax-m3"
        assert client.base_url == "https://api.inferhub.dev/v1"
        assert client.api_key == "sk-airo-test-key"

        # LLM_MODEL override works.
        os.environ["LLM_MODEL"] = "ocg/minimax-m2.5"
        client = build_client()
        assert client.model == "ocg/minimax-m2.5"
    finally:
        for k, v in saved.items():
            os.environ[k] = v
        os.environ.pop("LLM_MODEL", None)
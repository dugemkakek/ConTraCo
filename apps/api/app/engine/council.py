"""AI Council — six roles, all powered by the configured LLM brain.

Each role is now a thin adapter that asks the configured
``app.services.llm`` client for a JSON opinion and validates it into
a :class:`ModelOpinionData`.  The default brain is ``ocg/minimax-m3``
served via InferHub's OpenAI-compatible endpoint, falling back to a
deterministic :class:`StubClient` when ``LLM_API_KEY`` is unset so the
server stays runnable offline.

The 6 roles and their framing (each lives in
``app.services.llm.prompts.SYSTEM_TEMPLATES``):
  * technical_analyst       — reads classical TA, structure, momentum
  * market_context_analyst  — weighs regime + volume + structure
  * risk_reviewer           — looks for veto conditions (capped 0.35)
  * skeptical_reviewer      — argues *against* the consensus (capped 0.35)
  * trade_planner           — non-directional; runs after the decision
  * synthesis_reviewer      — non-directional; runs after the decision

``trade_planner`` and ``synthesis_reviewer`` still short-circuit to a
WAIT/VALID opinion without calling the LLM — they only contribute
their ``raw_output`` as part of the post-decision run summary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.db.models import Direction, ModelStatus
from app.services.llm import LLMClient, LLMError, build_client
from app.services.llm.prompts import build_role_prompt

logger = logging.getLogger(__name__)


# Role weights + caps are enforced from the strategy spec (NOT from
# whatever the model returns).  These are the spec-default values
# from ``app.engine.strategy.DEFAULT_CONFIG``.
ROLE_SPEC_DEFAULTS: dict[str, tuple[float, float]] = {
    "technical_analyst": (0.34, 1.0),
    "market_context_analyst": (0.22, 1.0),
    "risk_reviewer": (0.24, 0.35),
    "skeptical_reviewer": (0.20, 0.35),
    "trade_planner": (0.0, 1.0),
    "synthesis_reviewer": (0.0, 1.0),
}


@dataclass
class ModelOpinionData:
    """Lightweight, plain-dataclass opinion record.

    Kept distinct from ``ModelOpinionLike`` in ``decision.py`` to avoid
    pickle/import-cache issues between the engine and the runner.
    The runner reads these via duck-typing (``role``, ``status``,
    ``direction``, ``confidence``, ``role_weight``, ``confidence_cap``,
    ``risk_flags``, ``evidence_ids``, ``reason``) when building the
    persisted ``ModelOpinion`` rows.
    """

    role: str
    status: ModelStatus
    direction: Direction
    confidence: float
    role_weight: float
    confidence_cap: float
    risk_flags: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    reason: str = ""
    # Where this opinion came from. The runner copies this into
    # ``ModelOpinionRow.raw_output["provider_used"]`` so the UI can
    # display "Brain: ocg/minimax-m3 (ocg-stub)" next to each role.
    provider_used: str = "unknown"
    llm_model: str = ""

    @property
    def is_valid(self) -> bool:
        return self.status == ModelStatus.VALID


@dataclass
class CouncilContext:
    symbol: str
    timeframe: str
    candles: list
    gates: list
    symbol_meta: dict = field(default_factory=dict)
    order_book: dict | None = None
    recent_news: list[str] = field(default_factory=list)
    fundamental_context: str = ""


class CouncilRole(Protocol):
    name: str
    directional: bool

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData: ...


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _parse_status(raw: Any) -> ModelStatus:
    s = str(raw or "").upper().strip()
    if s in {"VALID", "PASS", "OK", "TRUE", "YES", "CONFIDENT"}:
        return ModelStatus.VALID
    if s in {"INVALID", "FAIL", "FAILED", "ERROR", "NO", "FALSE", "VETO"}:
        return ModelStatus.INVALID
    return ModelStatus.MISSING


def _parse_direction(raw: Any) -> Direction:
    s = str(raw or "").upper().strip()
    if s in {"LONG", "BUY", "BULLISH", "UP", "BULL"}:
        return Direction.LONG
    if s in {"SHORT", "SELL", "BEARISH", "DOWN", "BEAR"}:
        return Direction.SHORT
    return Direction.WAIT


def _valid_risk_flags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    allowed = {"data_integrity", "liquidity_trap", "manipulation_suspected"}
    return [str(x) for x in raw if str(x) in allowed]


def _coerce_evidence_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw][:8]


async def _ask_llm(
    role: str, ctx: CouncilContext, client: LLMClient
) -> ModelOpinionData:
    """Shared adapter logic for the 4 directional roles."""
    weight, cap = ROLE_SPEC_DEFAULTS.get(role, (0.0, 1.0))
    fallback = ModelOpinionData(
        role=role,
        status=ModelStatus.MISSING,
        direction=Direction.WAIT,
        confidence=0.0,
        role_weight=weight,
        confidence_cap=cap,
        reason=f"no evidence for {role}",
        provider_used=client.name,
        llm_model=client.model,
    )
    system, user = build_role_prompt(role, ctx)
    try:
        payload = await client.chat_json(system, user)
    except LLMError as exc:
        logger.warning("LLM call failed for role %s: %s", role, exc)
        return ModelOpinionData(
            role=role,
            status=ModelStatus.MISSING,
            direction=Direction.WAIT,
            confidence=0.0,
            role_weight=weight,
            confidence_cap=cap,
            reason=f"llm_error: {exc}",
            provider_used=client.name,
            llm_model=client.model,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected LLM error for role %s", role)
        return ModelOpinionData(
            role=role,
            status=ModelStatus.MISSING,
            direction=Direction.WAIT,
            confidence=0.0,
            role_weight=weight,
            confidence_cap=cap,
            reason=f"unexpected_error: {exc}",
            provider_used=client.name,
            llm_model=client.model,
        )

    if not isinstance(payload, dict):
        return fallback

    confidence = _clamp(
        float(payload.get("confidence", 0.0) or 0.0), 0.0, cap
    )
    direction = _parse_direction(payload.get("direction"))
    status = _parse_status(payload.get("status"))
    risk_flags = _valid_risk_flags(payload.get("risk_flags"))

    # Veto-capable roles (risk_reviewer) use status=INVALID as the
    # natural way to say "I'm flagging risk and abstaining on direction".
    # A bare INVALID with no risk_flags IS a true abstention and should
    # still collapse to MISSING. With risk_flags, the role has spoken —
    # keep it as VALID so the decision engine sees the veto signal.
    if status == ModelStatus.INVALID and not risk_flags:
        status = ModelStatus.MISSING
    elif status == ModelStatus.INVALID and risk_flags:
        # Preserve the abstention-as-veto: status VALID, but
        # confidence is zero'd below so the directional vote is null.
        status = ModelStatus.VALID
        direction = Direction.WAIT
        confidence = 0.0

    return ModelOpinionData(
        role=role,
        status=status,
        direction=direction,
        confidence=confidence,
        role_weight=weight,
        confidence_cap=cap,
        risk_flags=risk_flags,
        evidence_ids=_coerce_evidence_ids(payload.get("evidence_ids")),
        reason=str(payload.get("reason", ""))[:512],
        provider_used=client.name,
        llm_model=client.model,
    )


# Module-level cached client. Lazy build so importing this module is
# side-effect free (tests can monkeypatch ``_CLIENT``).
_CLIENT: LLMClient | None = None


def get_client() -> LLMClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = build_client()
    return _CLIENT


def set_client(client: LLMClient | None) -> None:
    """Inject a custom client (used by tests + the conftest)."""
    global _CLIENT
    _CLIENT = client


class TechnicalAnalyst:
    name = "technical_analyst"
    directional = True

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        return await _ask_llm(self.name, ctx, get_client())


class MarketContextAnalyst:
    name = "market_context_analyst"
    directional = True

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        return await _ask_llm(self.name, ctx, get_client())


class RiskReviewer:
    name = "risk_reviewer"
    directional = True

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        opinion = await _ask_llm(self.name, ctx, get_client())
        # Veto-capable role: any model-reported risk flag is already
        # preserved on ``opinion.risk_flags``; the decision engine
        # cross-checks them against ``hard_veto_risk_flags`` in the
        # spec.
        return opinion


class SkepticalReviewer:
    name = "skeptical_reviewer"
    directional = True

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        return await _ask_llm(self.name, ctx, get_client())


class TradePlanner:
    name = "trade_planner"
    directional = False

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        client = get_client()
        return ModelOpinionData(
            role=self.name,
            status=ModelStatus.VALID,
            direction=Direction.WAIT,
            confidence=1.0,
            role_weight=0.0,
            confidence_cap=1.0,
            reason="non-directional planner; no vote",
            provider_used=client.name,
            llm_model=client.model,
        )


class SynthesisReviewer:
    name = "synthesis_reviewer"
    directional = False

    async def evaluate(self, ctx: CouncilContext) -> ModelOpinionData:
        client = get_client()
        return ModelOpinionData(
            role=self.name,
            status=ModelStatus.VALID,
            direction=Direction.WAIT,
            confidence=1.0,
            role_weight=0.0,
            confidence_cap=1.0,
            reason="non-directional synthesis; no vote",
            provider_used=client.name,
            llm_model=client.model,
        )


DIRECTIONAL_ROLES = [TechnicalAnalyst(), MarketContextAnalyst(), RiskReviewer(), SkepticalReviewer()]
NON_DIRECTIONAL_ROLES = [TradePlanner(), SynthesisReviewer()]
ALL_ROLES = DIRECTIONAL_ROLES + NON_DIRECTIONAL_ROLES


async def run_council(ctx: CouncilContext) -> list[ModelOpinionData]:
    out: list[ModelOpinionData] = []
    for role in ALL_ROLES:
        out.append(await role.evaluate(ctx))
    return out


__all__ = [
    "ALL_ROLES",
    "CouncilContext",
    "DIRECTIONAL_ROLES",
    "MarketContextAnalyst",
    "ModelOpinionData",
    "NON_DIRECTIONAL_ROLES",
    "RiskReviewer",
    "SkepticalReviewer",
    "SynthesisReviewer",
    "TechnicalAnalyst",
    "TradePlanner",
    "ROLE_SPEC_DEFAULTS",
    "get_client",
    "run_council",
    "set_client",
]
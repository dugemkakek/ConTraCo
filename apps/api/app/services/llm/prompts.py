"""Prompt construction for the LLM-backed council.

Each role gets its own system prompt describing the framing the model
should adopt (technical, context, risk, skeptic, planner, synthesis).
The user prompt is a compact, deterministic serialization of the gate
evaluations + symbol/timeframe so the model has the same evidence no
matter how many times it is asked.

The response shape is always a JSON object with these fields:
  status       : "VALID" | "MISSING" | "INVALID"
  direction    : "LONG" | "SHORT" | "WAIT"
  confidence   : float in [0.0, 1.0]
  risk_flags   : list[str]   (any of: data_integrity, liquidity_trap,
                             manipulation_suspected)
  evidence_ids : list[str]   (gate names the model used)
  reason       : short free-text explanation (one sentence)

The role adapter in ``app.engine.council`` enforces the role's
``role_weight`` and ``confidence_cap`` from the strategy spec; the
model's own values for those fields are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.db.models import GateStatus


SYSTEM_TEMPLATES: dict[str, str] = {
    "technical_analyst": (
        "You are a TECHNICAL ANALYST reviewing classical TA, market "
        "structure, and momentum evidence for a crypto pair. "
        "Return only a JSON object with status, direction, confidence, "
        "risk_flags, evidence_ids, reason. Confidence cap is 1.0; "
        "be specific about which gate names influenced the call."
    ),
    "market_context_analyst": (
        "You are a MARKET CONTEXT ANALYST weighing market regime, "
        "volume, and order-book context for a crypto pair. "
        "Return only a JSON object with status, direction, confidence, "
        "risk_flags, evidence_ids, reason. Confidence cap is 1.0; "
        "highlight macro/regime signals."
    ),
    "risk_reviewer": (
        "You are a RISK REVIEWER with veto authority. Look for "
        "liquidity traps, manipulation risk, data integrity issues. "
        "Return only a JSON object. Confidence cap is 0.35. "
        "Set risk_flags to any of: data_integrity, liquidity_trap, "
        "manipulation_suspected."
    ),
    "skeptical_reviewer": (
        "You are a SKEPTICAL REVIEWER arguing AGAINST the consensus. "
        "If other roles lean long, argue short; if they lean short, "
        "argue long. Return only a JSON object. Confidence cap is 0.35. "
        "Use reason to spell out the counter-argument."
    ),
    "trade_planner": (
        "You are a TRADE PLANNER. You do NOT cast a directional vote. "
        "Return status=VALID, direction=WAIT, confidence=1.0, "
        "and put any execution caveats in reason."
    ),
    "synthesis_reviewer": (
        "You are a SYNTHESIS REVIEWER. You do NOT cast a directional "
        "vote. Return status=VALID, direction=WAIT, confidence=1.0, "
        "and put the one-sentence synthesis in reason."
    ),
}


@dataclass
class _GateRow:
    name: str
    status: str
    score: float
    confidence: float
    reason: str


def _serialize_gates(gates: Iterable) -> list[_GateRow]:
    out: list[_GateRow] = []
    for g in gates or []:
        status = (
            g.status.value
            if hasattr(g.status, "value")
            else str(getattr(g, "status", "UNAVAILABLE"))
        )
        out.append(
            _GateRow(
                name=getattr(g, "name", "unknown"),
                status=status,
                score=float(getattr(g, "score", 0.0)),
                confidence=float(getattr(g, "confidence", 0.0)),
                reason=str(getattr(g, "reason", ""))[:160],
            )
        )
    return out


def _last_close_stats(candles) -> str:
    """Cheap textual summary of the most recent candles."""
    if not candles:
        return "no candle data"
    last_n = candles[-5:]
    parts = []
    for c in last_n:
        try:
            parts.append(
                f"close={float(c.close):.2f} vol={float(c.volume):.2f}"
            )
        except Exception:  # noqa: BLE001
            continue
    return "; ".join(parts) or "no numeric candle data"


def build_role_prompt(role: str, ctx) -> tuple[str, str]:
    """Return (system, user) prompts for a single role.

    ``ctx`` is a :class:`app.engine.council.CouncilContext`; the type
    is intentionally untyped so this module stays free of an import
    dependency on the engine (which keeps the bytecode-cache footgun
    from biting).
    """
    system = SYSTEM_TEMPLATES.get(
        role,
        "You are an AI trading reviewer. Return only the requested JSON.",
    )

    rows = _serialize_gates(getattr(ctx, "gates", []))
    gate_lines = [
        f"- {r.name}: status={r.status} score={r.score:+.1f} "
        f"confidence={r.confidence:.2f} reason={r.reason!r}"
        for r in rows
    ]
    if not gate_lines:
        gate_lines = ["- (no gates produced)"]

    order_book = getattr(ctx, "order_book", None)
    if isinstance(order_book, dict):
        ob_summary = (
            f"order_book bids={len(order_book.get('bids', []))} "
            f"asks={len(order_book.get('asks', []))}"
        )
    else:
        ob_summary = "no order book"

    user = (
        f"Symbol: {getattr(ctx, 'symbol', '?')}\n"
        f"Timeframe: {getattr(ctx, 'timeframe', '?')}\n"
        f"Order book: {ob_summary}\n"
        f"Recent candles: {_last_close_stats(getattr(ctx, 'candles', []))}\n"
        + (
            f"\nFundamental context:\n{getattr(ctx, 'fundamental_context', '')}\n"
            if getattr(ctx, 'fundamental_context', '')
            else ""
        )
        + f"\nGate evaluations:\n" + "\n".join(gate_lines) + "\n"
        f"\nDecide as the {role} role. Respond with a single JSON object "
        "matching the schema in the system prompt. Do NOT include any "
        "prose outside the JSON."
    )
    return system, user


def gate_status_value(status) -> str:
    """Helper used by tests: normalise enum / string to its string value."""
    if isinstance(status, GateStatus):
        return status.value
    return str(status)


__all__ = ["build_role_prompt", "gate_status_value", "SYSTEM_TEMPLATES"]
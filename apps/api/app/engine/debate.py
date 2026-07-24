"""CRO Debate Protocol (spec 03).

Groups gate verdicts + council opinions into Bull / Bear / Neutral camps.
Flags low-conviction gates (confidence < floor). Generates per-side
natural-language summaries. Produces primary scenario, alternative
scenario, and invalidation condition.

This is the "Chief Risk Officer" synthesis layer — it doesn't compute
scores (that's confluence.py), it frames the debate for human consumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.confluence import GateVerdict, ScenarioFrame

# Confidence floor: below this, a gate is "low conviction" and
# visually deprioritized in the debate view (still counted in score).
LOW_CONVICTION_FLOOR = 0.3


@dataclass
class CampMember:
    name: str
    direction: int          # -1, 0, 1
    confidence: float
    weight: float
    reasoning: str
    low_conviction: bool = False
    source: str = "gate"    # "gate", "council", or "news"


@dataclass
class DebateCamp:
    label: str              # "BULL", "BEAR", "NEUTRAL"
    members: list[CampMember] = field(default_factory=list)

    @property
    def total_weight(self) -> float:
        return sum(m.weight for m in self.members)

    @property
    def avg_confidence(self) -> float:
        if not self.members:
            return 0.0
        return sum(m.confidence for m in self.members) / len(self.members)

    @property
    def high_conviction(self) -> list[CampMember]:
        return [m for m in self.members if not m.low_conviction]

    def summary(self) -> str:
        """One-paragraph natural-language summary of this camp's argument."""
        if not self.members:
            return f"No {self.label.lower()} arguments."
        hc = self.high_conviction
        lc = [m for m in self.members if m.low_conviction]
        parts = []
        if hc:
            names = ", ".join(m.name for m in hc[:4])
            avg_c = sum(m.confidence for m in hc) / len(hc)
            parts.append(
                f"{len(hc)} high-conviction {self.label.lower()} signal(s) "
                f"({names}; avg confidence {avg_c:.0%})"
            )
        if lc:
            parts.append(
                f"{len(lc)} low-conviction signal(s) deprioritized"
            )
        return ". ".join(parts) + "."


@dataclass
class DebateResult:
    bull_camp: DebateCamp
    bear_camp: DebateCamp
    neutral_camp: DebateCamp
    scenario: ScenarioFrame
    low_conviction_flags: list[str] = field(default_factory=list)
    debate_summary: str = ""
    news_sentiment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bull": {
                "members": [
                    {"name": m.name, "confidence": round(m.confidence, 3),
                     "weight": round(m.weight, 3), "reasoning": m.reasoning,
                     "low_conviction": m.low_conviction, "source": m.source}
                    for m in self.bull_camp.members
                ],
                "summary": self.bull_camp.summary(),
                "total_weight": round(self.bull_camp.total_weight, 4),
            },
            "bear": {
                "members": [
                    {"name": m.name, "confidence": round(m.confidence, 3),
                     "weight": round(m.weight, 3), "reasoning": m.reasoning,
                     "low_conviction": m.low_conviction, "source": m.source}
                    for m in self.bear_camp.members
                ],
                "summary": self.bear_camp.summary(),
                "total_weight": round(self.bear_camp.total_weight, 4),
            },
            "neutral": {
                "members": [
                    {"name": m.name, "confidence": round(m.confidence, 3),
                     "weight": round(m.weight, 3), "reasoning": m.reasoning,
                     "low_conviction": m.low_conviction, "source": m.source}
                    for m in self.neutral_camp.members
                ],
                "summary": self.neutral_camp.summary(),
                "total_weight": round(self.neutral_camp.total_weight, 4),
            },
            "scenario": {
                "primary": self.scenario.primary,
                "alternative": self.scenario.alternative,
                "invalidation": self.scenario.invalidation,
            },
            "low_conviction_flags": self.low_conviction_flags,
            "debate_summary": self.debate_summary,
            "news_sentiment": self.news_sentiment,
        }


def run_debate(
    verdicts: list[GateVerdict],
    scenario: ScenarioFrame,
    council_opinions: list[dict[str, Any]] | None = None,
    low_conviction_floor: float = LOW_CONVICTION_FLOOR,
    news_sentiment: dict[str, Any] | None = None,
) -> DebateResult:
    """Run the CRO debate protocol.

    Args:
        verdicts: gate verdicts from confluence engine
        scenario: scenario frame from confluence engine
        council_opinions: optional list of council opinion dicts
            with keys: role, direction (LONG/SHORT/WAIT), confidence, reason
        low_conviction_floor: confidence threshold for "low conviction" flag
        news_sentiment: optional VADER news payload from the
            fundamental_context gate (``evidence["news"]``). Surfaced as a
            weight-0 informational camp member plus a UI payload; payloads
            with an ``error`` key or zero articles are ignored.
    """
    bull = DebateCamp(label="BULL")
    bear = DebateCamp(label="BEAR")
    neutral = DebateCamp(label="NEUTRAL")
    low_flags: list[str] = []

    # Group gate verdicts
    for v in verdicts:
        lc = v.confidence < low_conviction_floor
        member = CampMember(
            name=v.gate_name,
            direction=v.direction,
            confidence=v.confidence,
            weight=v.weight,
            reasoning=v.reasoning,
            low_conviction=lc,
            source="gate",
        )
        if lc:
            low_flags.append(f"{v.gate_name} (conf={v.confidence:.2f})")
        if v.direction > 0:
            bull.members.append(member)
        elif v.direction < 0:
            bear.members.append(member)
        else:
            neutral.members.append(member)

    # Group council opinions (if provided)
    if council_opinions:
        for op in council_opinions:
            role = op.get("role", "unknown")
            dir_str = str(op.get("direction", "WAIT")).upper()
            conf = float(op.get("confidence", 0.0))
            reason = op.get("reason", "")
            direction = 1 if dir_str in ("LONG", "BUY", "BULLISH") else \
                        -1 if dir_str in ("SHORT", "SELL", "BEARISH") else 0
            lc = conf < low_conviction_floor
            member = CampMember(
                name=role,
                direction=direction,
                confidence=conf,
                weight=0.0,  # council opinions don't carry gate weight
                reasoning=reason,
                low_conviction=lc,
                source="council",
            )
            if lc:
                low_flags.append(f"{role} (conf={conf:.2f})")
            if direction > 0:
                bull.members.append(member)
            elif direction < 0:
                bear.members.append(member)
            else:
                neutral.members.append(member)

    # Surface VADER news sentiment from the fundamental_context gate.
    # Informational only: weight 0, never affects the confluence score —
    # it just joins the debate so the UI can show what the headlines say.
    news_payload: dict[str, Any] | None = None
    if (
        news_sentiment
        and "error" not in news_sentiment
        and news_sentiment.get("total_articles")
    ):
        label = str(news_sentiment.get("sentiment_label", "neutral")).lower()
        direction = 1 if label == "bullish" else -1 if label == "bearish" else 0
        compound = float(news_sentiment.get("mean_compound", 0.0) or 0.0)
        n_bull = int(news_sentiment.get("bullish", 0) or 0)
        n_bear = int(news_sentiment.get("bearish", 0) or 0)
        n_total = int(news_sentiment.get("total_articles", 0) or 0)
        conf = min(abs(compound) * 2.0, 1.0)
        lc = conf < low_conviction_floor
        member = CampMember(
            name="news_sentiment",
            direction=direction,
            confidence=conf,
            weight=0.0,
            reasoning=(
                f"News sentiment {label} (compound {compound:+.3f}): "
                f"{n_bull} bullish / {n_bear} bearish across {n_total} headlines."
            ),
            low_conviction=lc,
            source="news",
        )
        if lc:
            low_flags.append(f"news_sentiment (conf={conf:.2f})")
        if direction > 0:
            bull.members.append(member)
        elif direction < 0:
            bear.members.append(member)
        else:
            neutral.members.append(member)
        news_payload = news_sentiment

    # Sort each camp by confidence descending
    for camp in (bull, bear, neutral):
        camp.members.sort(key=lambda m: m.confidence, reverse=True)

    # Build debate summary
    bull_w = bull.total_weight
    bear_w = bear.total_weight
    total_w = bull_w + bear_w
    if total_w > 0:
        bull_pct = bull_w / total_w * 100
        bear_pct = bear_w / total_w * 100
    else:
        bull_pct = bear_pct = 50.0

    debate_summary = (
        f"Debate: {len(bull.members)} bull vs {len(bear.members)} bear "
        f"vs {len(neutral.members)} neutral. "
        f"Weighted split: {bull_pct:.0f}% bull / {bear_pct:.0f}% bear. "
        f"{len(low_flags)} low-conviction signal(s) flagged."
    )

    return DebateResult(
        bull_camp=bull,
        bear_camp=bear,
        neutral_camp=neutral,
        scenario=scenario,
        low_conviction_flags=low_flags,
        debate_summary=debate_summary,
        news_sentiment=news_payload,
    )


__all__ = [
    "CampMember",
    "DebateCamp",
    "DebateResult",
    "LOW_CONVICTION_FLOOR",
    "run_debate",
]

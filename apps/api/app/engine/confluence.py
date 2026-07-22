"""Confluence Engine — spec 04 implementation.

Locked formula:
    C_total = (Σ(weight_i × direction_i × confidence_i) / Σ weight_i) × 100

Score bands:
    ≥ 75  Strong      (green, alert-eligible)
    50-74 Moderate    (yellow, watch not act)
    < 50  Divergent   (red, no trade)

Regime-weighted variant:
    weight_i_effective = weight_i × regime_multiplier(gate_i, regime)

MTC bonus: +12% if HTF/MTF/LTF align, capped at 100.

Every output includes: primary scenario, alternative scenario,
invalidation trigger.  This is mandatory, not optional formatting.

Kelly: f* = (bp - q) / b, half-Kelly default, N≥30 sample gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Score bands (locked)
# ---------------------------------------------------------------------------

class ScoreBand(str, Enum):
    STRONG = "STRONG"        # ≥ 75
    MODERATE = "MODERATE"    # 50–74
    DIVERGENT = "DIVERGENT"  # < 50


def classify_band(abs_score: float) -> ScoreBand:
    if abs_score >= 75:
        return ScoreBand.STRONG
    if abs_score >= 50:
        return ScoreBand.MODERATE
    return ScoreBand.DIVERGENT


BAND_COLORS: dict[ScoreBand, str] = {
    ScoreBand.STRONG: "#10B981",     # emerald
    ScoreBand.MODERATE: "#F59E0B",   # amber
    ScoreBand.DIVERGENT: "#F43F5E",  # rose
}


# ---------------------------------------------------------------------------
# Regime detection + multiplier table
# ---------------------------------------------------------------------------

class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"


def detect_regime(adx: float, atr_pct: float) -> MarketRegime:
    """Classify regime from ADX + ATR%.

    ADX ≥ 25 → trending.  ATR% > 3% → high vol.  Both low → low vol.
    """
    if adx >= 25 and atr_pct > 3.0:
        return MarketRegime.HIGH_VOL
    if adx >= 25:
        return MarketRegime.TRENDING
    if atr_pct > 3.0:
        return MarketRegime.HIGH_VOL
    if atr_pct < 1.0:
        return MarketRegime.LOW_VOL
    return MarketRegime.RANGING


# Regime multiplier table: gate_name → {regime → multiplier}.
# Gates not listed default to 1.0 for all regimes.
# ponytail: tune these after 30+ logged recommendations; upgrade path
# is per-gate learned multipliers from the leaderboard.
REGIME_MULTIPLIERS: dict[str, dict[MarketRegime, float]] = {
    "classical_ta": {
        MarketRegime.TRENDING: 1.3,
        MarketRegime.RANGING: 0.8,
        MarketRegime.HIGH_VOL: 0.9,
        MarketRegime.LOW_VOL: 1.0,
    },
    "market_structure": {
        MarketRegime.TRENDING: 0.8,
        MarketRegime.RANGING: 1.3,
        MarketRegime.HIGH_VOL: 1.0,
        MarketRegime.LOW_VOL: 1.1,
    },
    "market_structure_smc": {
        MarketRegime.TRENDING: 0.8,
        MarketRegime.RANGING: 1.3,
        MarketRegime.HIGH_VOL: 1.0,
        MarketRegime.LOW_VOL: 1.1,
    },
    "volume_momentum": {
        MarketRegime.TRENDING: 1.2,
        MarketRegime.RANGING: 0.9,
        MarketRegime.HIGH_VOL: 1.1,
        MarketRegime.LOW_VOL: 0.8,
    },
    "funding_rate": {
        MarketRegime.TRENDING: 1.2,
        MarketRegime.RANGING: 0.9,
        MarketRegime.HIGH_VOL: 1.3,
        MarketRegime.LOW_VOL: 0.8,
    },
    "orderbook_micro": {
        MarketRegime.TRENDING: 1.0,
        MarketRegime.RANGING: 1.2,
        MarketRegime.HIGH_VOL: 1.1,
        MarketRegime.LOW_VOL: 0.9,
    },
    "liquidity_heatmap": {
        MarketRegime.TRENDING: 1.0,
        MarketRegime.RANGING: 1.1,
        MarketRegime.HIGH_VOL: 1.3,
        MarketRegime.LOW_VOL: 0.8,
    },
    "pattern_recognition": {
        MarketRegime.TRENDING: 1.1,
        MarketRegime.RANGING: 1.2,
        MarketRegime.HIGH_VOL: 0.8,
        MarketRegime.LOW_VOL: 1.0,
    },
}


def regime_multiplier(gate_name: str, regime: MarketRegime) -> float:
    return REGIME_MULTIPLIERS.get(gate_name, {}).get(regime, 1.0)


# ---------------------------------------------------------------------------
# Gate verdict (spec 03 agent contract)
# ---------------------------------------------------------------------------

@dataclass
class GateVerdict:
    """Structured verdict from a single gate agent.

    direction: -1 (short), 0 (neutral), +1 (long)
    confidence: 0..1
    weight: configurable, default 1.0
    """
    gate_name: str
    direction: int          # -1, 0, 1
    confidence: float       # 0..1
    weight: float = 1.0
    reasoning: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    gate_version: str = "1.0"
    timestamp: str = ""

    @property
    def weighted_contribution(self) -> float:
        return self.weight * self.direction * self.confidence


# ---------------------------------------------------------------------------
# Core confluence formula (locked)
# ---------------------------------------------------------------------------

def compute_confluence(
    verdicts: list[GateVerdict],
    regime: MarketRegime | None = None,
) -> float:
    """C_total = (Σ(w_eff_i × d_i × c_i) / Σ w_eff_i) × 100

    Returns score in [-100, 100].
    """
    if not verdicts:
        return 0.0

    num = 0.0
    den = 0.0
    for v in verdicts:
        w_eff = v.weight
        if regime is not None:
            w_eff *= regime_multiplier(v.gate_name, regime)
        num += w_eff * v.direction * v.confidence
        den += w_eff

    if den == 0:
        return 0.0
    return (num / den) * 100.0


# ---------------------------------------------------------------------------
# MTC (Multi-Timeframe Confluence) bonus
# ---------------------------------------------------------------------------

MTC_BONUS = 12.0  # +12% when HTF/MTF/LTF align


def apply_mtc_bonus(
    score: float,
    htf_direction: int,
    mtf_direction: int,
    ltf_direction: int,
) -> tuple[float, bool]:
    """Apply MTC bonus if all three timeframes agree in direction.

    Returns (adjusted_score, bonus_applied).
    """
    if htf_direction == 0 or mtf_direction == 0 or ltf_direction == 0:
        return score, False
    if htf_direction == mtf_direction == ltf_direction:
        sign = 1.0 if score >= 0 else -1.0
        adjusted = score + sign * MTC_BONUS
        adjusted = max(-100.0, min(100.0, adjusted))
        return adjusted, True
    return score, False


# ---------------------------------------------------------------------------
# Scenario framing (mandatory per spec 00 + 04)
# ---------------------------------------------------------------------------

@dataclass
class ScenarioFrame:
    primary: str
    alternative: str
    invalidation: str


def build_scenario_frame(
    score: float,
    band: ScoreBand,
    verdicts: list[GateVerdict],
) -> ScenarioFrame:
    """Build primary / alternative / invalidation from gate verdicts."""
    bulls = [v for v in verdicts if v.direction > 0]
    bears = [v for v in verdicts if v.direction < 0]
    neutrals = [v for v in verdicts if v.direction == 0]

    direction = "LONG" if score > 0 else "SHORT" if score < 0 else "NO TRADE"
    abs_score = abs(score)

    # Primary scenario
    if band == ScoreBand.STRONG:
        primary = (
            f"Strong {direction} confluence ({abs_score:.0f}%). "
            f"{len(bulls)} bull vs {len(bears)} bear gates. "
            f"Recommendation: actionable {direction} setup."
        )
    elif band == ScoreBand.MODERATE:
        primary = (
            f"Moderate {direction} confluence ({abs_score:.0f}%). "
            f"Conditional — watch, not act. "
            f"Wait for confirmation or stronger alignment."
        )
    else:
        primary = (
            f"Divergent / no trade ({abs_score:.0f}%). "
            f"Gates disagree — {len(bulls)} bull, {len(bears)} bear, "
            f"{len(neutrals)} neutral. No actionable edge."
        )

    # Alternative scenario (what the minority argues)
    if score > 0 and bears:
        bear_names = ", ".join(v.gate_name for v in bears[:3])
        alt_conf = max(v.confidence for v in bears)
        alternative = (
            f"Bear case: {bear_names} argue SHORT "
            f"(max confidence {alt_conf:.0%}). "
            f"If they're right, expect reversal from current levels."
        )
    elif score < 0 and bulls:
        bull_names = ", ".join(v.gate_name for v in bulls[:3])
        alt_conf = max(v.confidence for v in bulls)
        alternative = (
            f"Bull case: {bull_names} argue LONG "
            f"(max confidence {alt_conf:.0%}). "
            f"If they're right, expect bounce from current levels."
        )
    else:
        alternative = "No meaningful minority opposition."

    # Invalidation trigger
    if score > 0:
        invalidation = (
            f"Invalidated if: price breaks below nearest support / "
            f"bear gates gain >60% confidence / "
            f"funding flips strongly negative."
        )
    elif score < 0:
        invalidation = (
            f"Invalidated if: price breaks above nearest resistance / "
            f"bull gates gain >60% confidence / "
            f"funding flips strongly positive."
        )
    else:
        invalidation = "N/A — no directional call to invalidate."

    return ScenarioFrame(
        primary=primary,
        alternative=alternative,
        invalidation=invalidation,
    )


# ---------------------------------------------------------------------------
# Kelly Criterion (spec 04 + 09)
# ---------------------------------------------------------------------------

@dataclass
class KellyResult:
    full_kelly: float       # f* = (bp - q) / b
    half_kelly: float       # f* / 2 (default suggestion)
    win_rate: float         # p
    payoff_odds: float      # b
    sample_size: int        # N
    sufficient_data: bool   # N ≥ 30


def compute_kelly(
    win_rate: float,
    payoff_odds: float,
    sample_size: int,
    min_sample: int = 30,
) -> KellyResult:
    """f* = (bp - q) / b.  Half-Kelly is the default suggestion.

    If sample_size < min_sample, uses conservative default (p=0.45).
    """
    if sample_size < min_sample:
        p = 0.45  # conservative default below threshold
        sufficient = False
    else:
        p = max(0.01, min(0.99, win_rate))
        sufficient = True

    q = 1.0 - p
    b = max(0.1, payoff_odds)

    full = (b * p - q) / b
    full = max(0.0, full)  # never negative → no trade
    half = full / 2.0

    return KellyResult(
        full_kelly=round(full, 4),
        half_kelly=round(half, 4),
        win_rate=p,
        payoff_odds=b,
        sample_size=sample_size,
        sufficient_data=sufficient,
    )


# ---------------------------------------------------------------------------
# Full confluence result
# ---------------------------------------------------------------------------

@dataclass
class ConfluenceResult:
    score: float                    # [-100, 100]
    band: ScoreBand
    color: str
    regime: MarketRegime | None
    mtc_bonus_applied: bool
    scenario: ScenarioFrame
    kelly: KellyResult | None
    verdicts: list[GateVerdict] = field(default_factory=list)
    gate_version: str = "1.0"

    @property
    def abs_score(self) -> float:
        return abs(self.score)

    @property
    def direction_label(self) -> str:
        if self.score > 0:
            return "LONG"
        if self.score < 0:
            return "SHORT"
        return "NO TRADE"

    @property
    def is_actionable(self) -> bool:
        return self.band == ScoreBand.STRONG

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "band": self.band.value,
            "color": self.color,
            "direction": self.direction_label,
            "regime": self.regime.value if self.regime else None,
            "mtc_bonus_applied": self.mtc_bonus_applied,
            "is_actionable": self.is_actionable,
            "scenario": {
                "primary": self.scenario.primary,
                "alternative": self.scenario.alternative,
                "invalidation": self.scenario.invalidation,
            },
            "kelly": {
                "full": self.kelly.full_kelly,
                "half": self.kelly.half_kelly,
                "win_rate": self.kelly.win_rate,
                "sample_size": self.kelly.sample_size,
                "sufficient_data": self.kelly.sufficient_data,
            } if self.kelly else None,
            "verdicts": [
                {
                    "gate": v.gate_name,
                    "direction": v.direction,
                    "confidence": round(v.confidence, 3),
                    "weight": round(v.weight, 3),
                    "reasoning": v.reasoning,
                }
                for v in self.verdicts
            ],
            "gate_version": self.gate_version,
        }


def run_confluence(
    verdicts: list[GateVerdict],
    *,
    regime: MarketRegime | None = None,
    htf_direction: int = 0,
    mtf_direction: int = 0,
    ltf_direction: int = 0,
    win_rate: float = 0.5,
    payoff_odds: float = 2.0,
    sample_size: int = 0,
    gate_version: str = "1.0",
) -> ConfluenceResult:
    """Full confluence pipeline: formula → MTC → band → scenario → Kelly."""
    score = compute_confluence(verdicts, regime)
    score, mtc_applied = apply_mtc_bonus(
        score, htf_direction, mtf_direction, ltf_direction
    )
    band = classify_band(abs(score))
    color = BAND_COLORS[band]
    scenario = build_scenario_frame(score, band, verdicts)
    kelly = compute_kelly(win_rate, payoff_odds, sample_size)

    return ConfluenceResult(
        score=score,
        band=band,
        color=color,
        regime=regime,
        mtc_bonus_applied=mtc_applied,
        scenario=scenario,
        kelly=kelly,
        verdicts=verdicts,
        gate_version=gate_version,
    )


__all__ = [
    "BAND_COLORS",
    "ConfluenceResult",
    "GateVerdict",
    "KellyResult",
    "MTC_BONUS",
    "MarketRegime",
    "REGIME_MULTIPLIERS",
    "ScenarioFrame",
    "ScoreBand",
    "apply_mtc_bonus",
    "build_scenario_frame",
    "classify_band",
    "compute_confluence",
    "compute_kelly",
    "detect_regime",
    "regime_multiplier",
    "run_confluence",
]

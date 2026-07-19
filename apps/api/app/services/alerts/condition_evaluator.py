"""Alert condition evaluator — price, indicator, gate score, pattern conditions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_condition(
    condition_type: str,
    params: dict[str, Any],
    current_price: float | None = None,
    gate_scores: dict[str, float] | None = None,
    indicator_values: dict[str, float] | None = None,
) -> tuple[bool, str]:
    """Evaluate a single alert condition. Returns (triggered, message)."""
    if condition_type == "price_above" and current_price and params.get("value"):
        if current_price >= params["value"]:
            return True, f"Price ${current_price:.2f} crossed above ${params['value']:.2f}"
    elif condition_type == "price_below" and current_price and params.get("value"):
        if current_price <= params["value"]:
            return True, f"Price ${current_price:.2f} crossed below ${params['value']:.2f}"
    elif condition_type == "gate_score_above" and gate_scores and params.get("gate") and params.get("score"):
        score = gate_scores.get(params["gate"], 0.0)
        if score >= params["score"]:
            return True, f"{params['gate']} score {score:.2f} >= {params['score']}"
    elif condition_type == "indicator" and indicator_values and params.get("indicator") and params.get("condition"):
        val = indicator_values.get(params["indicator"])
        if val is None:
            return False, ""
        threshold = params.get("value", 0)
        if params["condition"] == "cross_above" and val >= threshold:
            return True, f"{params['indicator']} {val:.1f} crossed above {threshold}"
        if params["condition"] == "cross_below" and val <= threshold:
            return True, f"{params['indicator']} {val:.1f} crossed below {threshold}"

    return False, ""

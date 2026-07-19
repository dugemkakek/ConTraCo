"""Multi-Timeframe Confluence Engine — runs analysis across 3 TFs and scores alignment."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.schemas.candle import Candle

logger = logging.getLogger(__name__)

TIMEFRAME_HIERARCHY: dict[str, dict[str, list[str]]] = {
    "scalp": {
        "entry": ["1m", "5m"],
        "structure": ["15m"],
        "bias": ["1h", "4h"],
    },
    "intraday": {
        "entry": ["5m", "15m"],
        "structure": ["1h"],
        "bias": ["4h", "1d"],
    },
    "swing": {
        "entry": ["1h", "4h"],
        "structure": ["4h", "1d"],
        "bias": ["1d", "1w"],
    },
}


@dataclass
class TFResult:
    timeframe: str
    gate_scores: dict[str, float]
    composite_score: float
    direction: str  # LONG | SHORT | WAIT

    reason: str = ""


@dataclass
class MTFResult:
    timeframes: dict[str, TFResult]
    confluence_score: float
    alignment: str  # "full" | "partial" | "conflicting"
    multiplier: float
    bias: str  # "bullish" | "bearish" | "neutral"
    details: str = ""


async def run_mtf_analysis(
    symbol: str,
    strategy_type: str,
    gate_evaluator_fn,
    candle_fetcher_fn,
) -> MTFResult:
    """Run gate analysis on entry/structure/bias timeframes in parallel."""
    hierarchy = TIMEFRAME_HIERARCHY.get(strategy_type, TIMEFRAME_HIERARCHY["intraday"])
    target_tfs: set[str] = set()
    for group in hierarchy.values():
        target_tfs.update(group)
    target_tfs_list = list(target_tfs)

    # Fetch candles for all TFs in parallel
    candle_tasks = [candle_fetcher_fn(symbol, tf, 300) for tf in target_tfs_list]
    all_candles = await asyncio.gather(*candle_tasks, return_exceptions=True)

    # Run gates on each TF in parallel
    tf_results: dict[str, TFResult] = {}
    for tf, candles_or_err in zip(target_tfs_list, all_candles):
        if isinstance(candles_or_err, Exception):
            logger.warning("MTF fetch failed for %s %s: %s", symbol, tf, candles_or_err)
            continue
        try:
            result = await gate_evaluator_fn(symbol, tf, candles_or_err)
            tf_results[tf] = result
        except Exception as exc:  # noqa: BLE001
            logger.warning("MTF gate eval failed for %s %s: %s", symbol, tf, exc)

    if not tf_results:
        return MTFResult(
            timeframes={},
            confluence_score=0.0,
            alignment="conflicting",
            multiplier=0.5,
            bias="neutral",
            details="No timeframe data available",
        )

    # Determine bias from bias TFs, direction from entry TFs
    bias_directions = [r.direction for tf, r in tf_results.items() if any(
        tf in hierarchy.get("bias", []) for _ in [1]
    )]
    entry_directions = [r.direction for tf, r in tf_results.items() if any(
        tf in hierarchy.get("entry", []) for _ in [1]
    )]

    # This is simplified — the full implementation is in the plan
    return MTFResult(
        timeframes=tf_results,
        confluence_score=0.0,
        alignment="partial",
        multiplier=1.0,
        bias="neutral",
        details="MTF analysis stub — see refinement plan for full implementation",
    )

"""Event-driven, no-lookahead backtesting using live gate implementations.

Signal is computed at bar close i from candles[:i+1]. Entry occurs at the next
bar open; exit occurs after ``holding_bars`` at that bar's close. LLM council
calls are intentionally excluded: backtests reuse deterministic gate math and
confluence weights, not costly narrative generation.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from app.db.models import GateStatus
from app.engine.confluence import GateVerdict, detect_regime, run_confluence
from app.engine.gates import ALL_GATES, GateContext, GateEvaluation
from app.engine.strategy import StrategyConfigSpec
from app.schemas.candle import Candle

GATE_VERSION = "1.0"
WARMUP_BARS = 200


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    confluence_threshold: float = 50.0
    holding_bars: int = 12
    position_fraction: float = 0.10
    fee_bps: float = 8.0
    slippage_bps: float = 5.0
    walk_forward_split: float = 0.70

    def validate(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if not 0 <= self.confluence_threshold <= 100:
            raise ValueError("confluence_threshold must be within 0..100")
        if self.holding_bars < 1:
            raise ValueError("holding_bars must be >= 1")
        if not 0 < self.position_fraction <= 1:
            raise ValueError("position_fraction must be within (0, 1]")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("cost assumptions cannot be negative")
        if not 0.5 <= self.walk_forward_split < 1:
            raise ValueError("walk_forward_split must be within [0.5, 1)")


@dataclass
class BacktestTrade:
    direction: str
    signal_index: int
    entry_index: int
    exit_index: int
    signal_time: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    confluence_score: float
    gross_return_pct: float
    net_return_pct: float
    pnl: float
    equity_after: float
    gate_attribution: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    gate_version: str
    config: BacktestConfig
    metrics: dict[str, Any]
    in_sample_metrics: dict[str, Any]
    out_of_sample_metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]
    benchmark_curve: list[dict[str, Any]]
    trades: list[BacktestTrade]
    per_gate_accuracy: dict[str, dict[str, Any]]
    actual_range: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "gate_version": self.gate_version,
            "config": asdict(self.config),
            "metrics": self.metrics,
            "walk_forward": {
                "split": self.config.walk_forward_split,
                "in_sample": self.in_sample_metrics,
                "out_of_sample": self.out_of_sample_metrics,
                "note": "weights remain pinned; compare OOS decay before manual tuning",
            },
            "equity_curve": self.equity_curve,
            "benchmark_curve": self.benchmark_curve,
            "trades": [asdict(t) for t in self.trades],
            "per_gate_accuracy": self.per_gate_accuracy,
            "actual_range": self.actual_range,
        }


async def evaluate_deterministic_gates(
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    spec: StrategyConfigSpec,
) -> tuple[list[GateEvaluation], Any]:
    """Call exact live gate objects against a point-in-time candle prefix."""
    ctx = GateContext(symbol=symbol, timeframe=timeframe, candles=candles)
    evaluations: list[GateEvaluation] = []
    for gate in ALL_GATES:
        try:
            evaluation = await gate.evaluate(ctx)
        except Exception as exc:  # noqa: BLE001
            evaluation = GateEvaluation(
                name=gate.name,
                status=GateStatus.UNAVAILABLE,
                score=0.0,
                confidence=0.0,
                reason=f"gate crashed: {exc}",
            )
        evaluations.append(evaluation)

    regime = None
    regime_eval = next(
        (g for g in evaluations if g.name == "market_regime" and g.status != GateStatus.UNAVAILABLE),
        None,
    )
    if regime_eval is not None:
        adx_value = float(regime_eval.evidence.get("adx", 0.0))
        recent = candles[-14:]
        atr_pct = (
            sum(c.high - c.low for c in recent)
            / max(len(recent), 1)
            / max(candles[-1].close, 1e-9)
            * 100
        )
        regime = detect_regime(adx_value, atr_pct)

    weights = spec.gates.model_dump()
    verdicts = [
        GateVerdict(
            gate_name=g.name,
            direction=1 if g.score > 5 else -1 if g.score < -5 else 0,
            confidence=g.confidence,
            weight=weights.get(g.name, 0.0),
            reasoning=g.reason,
            evidence=g.evidence,
            gate_version=GATE_VERSION,
        )
        for g in evaluations
        if g.status != GateStatus.UNAVAILABLE and weights.get(g.name, 0.0) > 0
    ]
    return evaluations, run_confluence(verdicts, regime=regime, gate_version=GATE_VERSION)


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return abs(worst)


def _metrics(trades: list[BacktestTrade], initial_equity: float) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "net_return_pct": 0.0,
            "win_rate": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "profit_factor": 0.0,
            "final_equity": round(initial_equity, 2),
        }
    returns = [t.net_return_pct / 100 for t in trades]
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]
    equity = [initial_equity] + [t.equity_after for t in trades]
    mean = statistics.fmean(returns)
    stdev = statistics.stdev(returns) if len(returns) > 1 else 0.0
    sharpe = mean / stdev * math.sqrt(len(returns)) if stdev else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (math.inf if wins else 0.0)
    final = trades[-1].equity_after
    return {
        "total_trades": len(trades),
        "net_return_pct": round((final / initial_equity - 1) * 100, 4),
        "win_rate": round(len(wins) / len(trades), 4),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "profit_factor": "Infinity" if math.isinf(profit_factor) else round(profit_factor, 4),
        "final_equity": round(final, 2),
    }


async def run_backtest(
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    spec: StrategyConfigSpec,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    config.validate()
    if len(candles) < WARMUP_BARS + config.holding_bars + 1:
        raise ValueError(
            f"need at least {WARMUP_BARS + config.holding_bars + 1} candles, got {len(candles)}"
        )
    ordered = sorted(candles, key=lambda c: c.timestamp)
    if any(a.timestamp >= b.timestamp for a, b in zip(ordered, ordered[1:])):
        raise ValueError("candle timestamps must be unique and strictly increasing")

    equity = config.initial_equity
    trades: list[BacktestTrade] = []
    equity_curve = [{"timestamp": ordered[WARMUP_BARS - 1].timestamp.isoformat(), "equity": equity}]
    benchmark_curve = [{"timestamp": ordered[WARMUP_BARS].timestamp.isoformat(), "equity": equity}]
    benchmark_entry = ordered[WARMUP_BARS].open
    gate_stats: dict[str, dict[str, int]] = {}
    round_trip_cost = 2 * (config.fee_bps + config.slippage_bps) / 10_000

    index = WARMUP_BARS - 1
    last_signal_index = len(ordered) - config.holding_bars - 2
    while index <= last_signal_index:
        prefix = ordered[: index + 1]
        evaluations, confluence = await evaluate_deterministic_gates(
            symbol, timeframe, prefix, spec
        )
        future_close = ordered[index + config.holding_bars + 1].close
        future_move = future_close / ordered[index].close - 1
        for gate in evaluations:
            direction = 1 if gate.score > 5 else -1 if gate.score < -5 else 0
            if direction == 0 or gate.status == GateStatus.UNAVAILABLE:
                continue
            stat = gate_stats.setdefault(gate.name, {"calls": 0, "correct": 0})
            stat["calls"] += 1
            if direction * future_move > 0:
                stat["correct"] += 1

        if abs(confluence.score) < config.confluence_threshold or confluence.score == 0:
            index += 1
            continue

        direction_value = 1 if confluence.score > 0 else -1
        entry_index = index + 1
        exit_index = entry_index + config.holding_bars
        entry_price = ordered[entry_index].open
        exit_price = ordered[exit_index].close
        gross_return = direction_value * (exit_price / entry_price - 1)
        net_return = gross_return - round_trip_cost
        pnl = equity * config.position_fraction * net_return
        equity += pnl
        contributions = {
            v.gate_name: round(v.weight * v.direction * v.confidence, 6)
            for v in confluence.verdicts
        }
        trades.append(BacktestTrade(
            direction="LONG" if direction_value > 0 else "SHORT",
            signal_index=index,
            entry_index=entry_index,
            exit_index=exit_index,
            signal_time=ordered[index].timestamp.isoformat(),
            entry_time=ordered[entry_index].timestamp.isoformat(),
            exit_time=ordered[exit_index].timestamp.isoformat(),
            entry_price=entry_price,
            exit_price=exit_price,
            confluence_score=round(confluence.score, 4),
            gross_return_pct=round(gross_return * 100, 4),
            net_return_pct=round(net_return * 100, 4),
            pnl=round(pnl, 4),
            equity_after=round(equity, 4),
            gate_attribution=contributions,
        ))
        equity_curve.append({"timestamp": ordered[exit_index].timestamp.isoformat(), "equity": round(equity, 4)})
        benchmark_equity = config.initial_equity * ordered[exit_index].close / benchmark_entry
        benchmark_curve.append({"timestamp": ordered[exit_index].timestamp.isoformat(), "equity": round(benchmark_equity, 4)})
        index = exit_index

    split_timestamp = ordered[int(len(ordered) * config.walk_forward_split)].timestamp
    in_sample = [t for t in trades if ordered[t.signal_index].timestamp < split_timestamp]
    out_sample = [t for t in trades if ordered[t.signal_index].timestamp >= split_timestamp]
    in_metrics = _metrics(in_sample, config.initial_equity)
    oos_initial = in_sample[-1].equity_after if in_sample else config.initial_equity
    oos_metrics = _metrics(out_sample, oos_initial)
    per_gate_accuracy = {
        name: {
            "calls": stat["calls"],
            "correct": stat["correct"],
            "accuracy": round(stat["correct"] / stat["calls"], 4) if stat["calls"] else 0.0,
        }
        for name, stat in sorted(gate_stats.items())
    }

    return BacktestResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        gate_version=GATE_VERSION,
        config=config,
        metrics=_metrics(trades, config.initial_equity),
        in_sample_metrics=in_metrics,
        out_of_sample_metrics=oos_metrics,
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        trades=trades,
        per_gate_accuracy=per_gate_accuracy,
        actual_range={
            "start": ordered[0].timestamp.isoformat(),
            "end": ordered[-1].timestamp.isoformat(),
            "walk_forward_split": split_timestamp.isoformat(),
        },
    )


__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "GATE_VERSION",
    "WARMUP_BARS",
    "evaluate_deterministic_gates",
    "run_backtest",
]

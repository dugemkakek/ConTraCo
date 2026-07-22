"""Gate framework.

A ``BaseGate`` consumes a list of OHLCV candles plus a ``GateContext``
(side data the engine assembles, e.g. order book snapshot, ATR
percentile, time-of-day) and returns a ``GateEvaluation``.

Every gate's output is the same shape, regardless of its internals —
that uniformity is what makes the engine auditable. A run stores
``(gate_name, status, score, weight, confidence, reason, evidence)``
per gate, and the decision math in ``app.engine.decision`` consumes
that table.

To add a new gate:
  1. Subclass ``BaseGate`` and set ``name``.
  2. Implement ``async evaluate(ctx)``.
  3. Register it in ``ALL_GATES`` below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.db.models import GateStatus


@dataclass
class GateEvaluation:
    name: str
    status: GateStatus
    score: float  # -100..100
    confidence: float  # 0..1
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def is_veto(self) -> bool:
        return self.status == GateStatus.VETO

    def is_directional(self) -> bool:
        return self.status in {GateStatus.PASS, GateStatus.FAIL}


class GateContext:
    """Everything a gate is allowed to read.

    Built by the engine runner before any gate fires. Candles are the
    universal input; everything else is best-effort and gates that
    can't compute on missing data must return ``UNAVAILABLE``.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        candles: list,
        order_book: dict | None = None,
        symbol_meta: dict | None = None,
        now_unix: int | None = None,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.candles = candles
        self.order_book = order_book
        self.symbol_meta = symbol_meta or {}
        self.now_unix = now_unix


class BaseGate(Protocol):
    name: str

    async def evaluate(self, ctx: GateContext) -> GateEvaluation: ...


from app.engine.gates.market_regime import MarketRegimeGate  # noqa: E402
from app.engine.gates.classical_ta import ClassicalTAGate  # noqa: E402
from app.engine.gates.market_structure import MarketStructureGate  # noqa: E402
from app.engine.gates.volume_momentum import VolumeMomentumGate  # noqa: E402
from app.engine.gates.fundamental_context import FundamentalContextGate  # noqa: E402
from app.engine.gates.risk_tradeability import RiskTradeabilityGate  # noqa: E402
from app.engine.gates.market_structure_smc import SMCStructureGate  # noqa: E402
from app.engine.gates.ichimoku_cloud import IchimokuCloudGate  # noqa: E402
from app.engine.gates.fibonacci_levels import FibonacciLevelsGate  # noqa: E402
from app.engine.gates.on_chain_flow import OnChainFlowGate  # noqa: E402
from app.engine.gates.funding_rate import FundingRateGate  # noqa: E402
from app.engine.gates.orderbook_micro import OrderbookMicroGate  # noqa: E402
from app.engine.gates.liquidity_heatmap import LiquidityHeatmapGate  # noqa: E402
from app.engine.gates.pattern_recognition import PatternRecognitionGate  # noqa: E402

ALL_GATES: list[BaseGate] = [
    MarketRegimeGate(),
    ClassicalTAGate(),
    MarketStructureGate(),
    VolumeMomentumGate(),
    FundamentalContextGate(),
    RiskTradeabilityGate(),
    SMCStructureGate(),
    IchimokuCloudGate(),
    FibonacciLevelsGate(),
    OnChainFlowGate(),
    FundingRateGate(),
    OrderbookMicroGate(),
    LiquidityHeatmapGate(),
    PatternRecognitionGate(),
]

GATE_NAMES = [g.name for g in ALL_GATES]

__all__ = [
    "ALL_GATES",
    "BaseGate",
    "GATE_NAMES",
    "GateContext",
    "GateEvaluation",
]

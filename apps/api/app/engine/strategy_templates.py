"""Strategy templates — battle-tested presets for different trading styles."""

from __future__ import annotations

from typing import Any

STRATEGY_TEMPLATES: dict[str, dict[str, Any]] = {
    "smc_scalper": {
        "name": "SMC Scalper",
        "description": "Smart Money Concepts for 1m-5m scalps. Uses order blocks, FVGs, and volume profile for entries.",
        "timeframes": ["1m", "5m"],
        "gates": ["smc_structure", "volume_momentum", "market_regime", "risk_tradeability"],
        "gate_weights": {
            "smc_structure": 0.3, "volume_momentum": 0.3,
            "market_regime": 0.2, "risk_tradeability": 0.2,
        },
        "score_threshold": 0.65,
        "default_rr": 2.0,
        "mtf_enabled": True,
        "mtf_type": "scalp",
    },
    "wyckoff_swing": {
        "name": "Wyckoff Swing",
        "description": "Wyckoff accumulation/distribution for 4h-1D swings. Patient entries at spring/test points.",
        "timeframes": ["4h", "1d"],
        "gates": ["market_regime", "fundamental_context", "risk_tradeability",
                  "fibonacci_levels", "ichimoku_cloud"],
        "gate_weights": {
            "market_regime": 0.2, "fundamental_context": 0.2,
            "risk_tradeability": 0.2, "fibonacci_levels": 0.2,
            "ichimoku_cloud": 0.2,
        },
        "score_threshold": 0.6,
        "default_rr": 3.0,
        "mtf_enabled": True,
        "mtf_type": "swing",
    },
    "full_confluence": {
        "name": "Full Confluence",
        "description": "All 9 gates. Maximum analysis depth. Slower but most thorough.",
        "timeframes": ["1h"],
        "gates": [],  # ALL_GATES at runtime
        "gate_weights": None,
        "score_threshold": 0.55,
        "default_rr": 2.5,
        "mtf_enabled": True,
        "mtf_type": "intraday",
    },
    "momentum_breakout": {
        "name": "Momentum Breakout",
        "description": "Catches breakouts with volume confirmation. Fast entries on momentum shifts.",
        "timeframes": ["15m", "1h"],
        "gates": ["volume_momentum", "market_structure", "classical_ta",
                  "smc_structure", "risk_tradeability"],
        "score_threshold": 0.7,
        "default_rr": 2.0,
    },
    "mean_reversion": {
        "name": "Mean Reversion",
        "description": "Fades extremes using RSI, Bollinger, and Fibonacci. Best in ranging markets.",
        "timeframes": ["1h", "4h"],
        "gates": ["classical_ta", "fibonacci_levels", "ichimoku_cloud",
                  "market_regime", "risk_tradeability"],
        "score_threshold": 0.65,
        "default_rr": 1.5,
    },
}

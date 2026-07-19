"""Build the configured market data provider and live candle stream.

Selection is env-driven so CI keeps using the deterministic Mock while
dev/prod can flip to live Gate.io data without code changes.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.market_data.base import MarketDataProvider
from app.services.market_data.gateio_rest import GateioRestProvider
from app.services.market_data.gateio_ws import CandleStream
from app.services.market_data.mock_provider import MockMarketDataProvider

logger = logging.getLogger(__name__)

_PROVIDER_KEYS = {
    "mock": "mock",
    "gateio": "gateio",
    "gate.io": "gateio",
}


def build_provider() -> MarketDataProvider:
    name = os.getenv("MARKET_DATA_PROVIDER", "mock").strip().lower()
    if name not in _PROVIDER_KEYS:
        raise RuntimeError(
            f"Unknown MARKET_DATA_PROVIDER={name!r}. Valid: {sorted(_PROVIDER_KEYS)}"
        )
    if _PROVIDER_KEYS[name] == "gateio":
        logger.info("Using Gate.io REST provider for market data")
        return GateioRestProvider()
    logger.info("Using Mock provider for market data")
    return MockMarketDataProvider()


def build_provider_for_venue(venue_id: str) -> MarketDataProvider:
    """Build a provider for a specific venue, bypassing the env var."""
    from app.services.market_data.registry import get_provider
    return get_provider(venue_id)


def build_stream(redis_client: Any | None = None) -> CandleStream:
    name = os.getenv("MARKET_DATA_PROVIDER", "mock").strip().lower()
    if _PROVIDER_KEYS.get(name) != "gateio":
        # No point opening a WS when we're serving from the mock provider.
        return CandleStream(ws_url="ws://invalid/_never_connect_", redis_client=redis_client)
    return CandleStream(redis_client=redis_client)


__all__ = ["build_provider", "build_stream", "build_provider_for_venue"]

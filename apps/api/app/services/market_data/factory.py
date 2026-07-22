"""Build the configured market data provider and live candle stream.

Selection is env-driven. Default is **Binance** (public market data, no
key required). The legacy ``mock`` value is preserved only for internal
fixtures and is rejected when ``CONTRA_CO_ALLOW_MOCK`` is not set.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.market_data.base import MarketDataProvider
from app.services.market_data.gateio_rest import GateioRestProvider
from app.services.market_data.gateio_ws import CandleStream

logger = logging.getLogger(__name__)

_PROVIDER_KEYS = {
    "binance": "binance",
    "gateio": "gateio",
    "gate.io": "gateio",
    "bybit": "bybit",
    "okx": "okx",
    "kraken": "kraken",
}

_MOCK_ALLOWED = os.getenv("CONTRA_CO_ALLOW_MOCK", "0") == "1"


def build_provider() -> MarketDataProvider:
    name = os.getenv("MARKET_DATA_PROVIDER", "binance").strip().lower()
    if name == "mock":
        if not _MOCK_ALLOWED:
            raise RuntimeError(
                "MARKET_DATA_PROVIDER=mock is no longer accepted; "
                "set CONTRA_CO_ALLOW_MOCK=1 to opt in (test fixtures only). "
                "Live Binance public data is the default."
            )
        from app.services.market_data.mock_provider import MockMarketDataProvider
        logger.warning("Using deterministic Mock provider — for tests/fixtures only")
        return MockMarketDataProvider()
    if name not in _PROVIDER_KEYS:
        raise RuntimeError(
            f"Unknown MARKET_DATA_PROVIDER={name!r}. Valid: {sorted(_PROVIDER_KEYS)}"
        )
    if _PROVIDER_KEYS[name] == "gateio":
        logger.info("Using Gate.io REST provider for market data")
        return GateioRestProvider()
    if _PROVIDER_KEYS[name] == "binance":
        logger.info("Using Binance public REST provider for market data")
        from app.services.market_data.binance_rest import BinanceRestProvider
        return BinanceRestProvider()
    if _PROVIDER_KEYS[name] == "bybit":
        logger.info("Using Bybit public REST provider for market data")
        from app.services.market_data.bybit_rest import BybitRestProvider
        return BybitRestProvider()
    if _PROVIDER_KEYS[name] == "okx":
        logger.info("Using OKX public REST provider for market data")
        from app.services.market_data.okx_rest import OkxRestProvider
        return OkxRestProvider()
    if _PROVIDER_KEYS[name] == "kraken":
        logger.info("Using Kraken public REST provider for market data")
        from app.services.market_data.kraken_rest import KrakenRestProvider
        return KrakenRestProvider()
    raise RuntimeError(f"unreachable: provider {name}")


def build_provider_for_venue(venue_id: str) -> MarketDataProvider:
    """Build a provider for a specific venue, bypassing the env var."""
    from app.services.market_data.registry import get_provider
    return get_provider(venue_id)


def build_stream(redis_client: Any | None = None) -> CandleStream:
    name = os.getenv("MARKET_DATA_PROVIDER", "binance").strip().lower()
    if _PROVIDER_KEYS.get(name) != "gateio":
        # Default — disable WS stream for non-gateio real-data paths.
        # The CandleStream stays constructable so call sites do not crash;
        # the runner uses REST polling for non-Gate.io venues.
        return CandleStream(ws_url="ws://invalid/_never_connect_", redis_client=redis_client)
    return CandleStream(redis_client=redis_client)


__all__ = ["build_provider", "build_stream", "build_provider_for_venue"]

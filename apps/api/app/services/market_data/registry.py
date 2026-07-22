"""Registry of available market-data providers / venues."""

from __future__ import annotations

from app.services.market_data.base import MarketDataProvider
from app.services.market_data.gateio_rest import GateioRestProvider
from app.services.market_data.binance_rest import BinanceRestProvider
from app.services.market_data.bybit_rest import BybitRestProvider
from app.services.market_data.kraken_rest import KrakenRestProvider
from app.services.market_data.okx_rest import OkxRestProvider

# Live-data venues only. The deterministic mock provider is used internally
# for fixtures and CI but never appears in the public UI.
_VENUE_REGISTRY: dict[str, type[MarketDataProvider]] = {
    "binance": BinanceRestProvider,
    "bybit": BybitRestProvider,
    "kraken": KrakenRestProvider,
    "okx": OkxRestProvider,
    "gateio": GateioRestProvider,
}


def list_venues() -> list[dict[str, str | bool]]:
    return [
        {
            "id": k,
            "label": cls.venue_label if hasattr(cls, "venue_label") else k,
            "enabled": True,
        }
        for k, cls in _VENUE_REGISTRY.items()
    ]


def get_provider(venue_id: str) -> MarketDataProvider:
    if venue_id not in _VENUE_REGISTRY:
        raise ValueError(f"Unknown venue: {venue_id!r}")
    return _VENUE_REGISTRY[venue_id]()


def all_providers() -> list[MarketDataProvider]:
    return [cls() for cls in _VENUE_REGISTRY.values()]

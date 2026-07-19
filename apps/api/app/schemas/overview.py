from __future__ import annotations

from pydantic import BaseModel


class TickerSnapshot(BaseModel):
    symbol: str
    last: float
    change_24h_pct: float | None
    high_24h: float | None
    low_24h: float | None
    volume_24h: float | None
    rsi_14: float | None
    trend: str  # "up" | "down" | "flat"
    sparkline: list[float]


class Breadth(BaseModel):
    up: int
    down: int
    flat: int


class Movers(BaseModel):
    gainers: list[TickerSnapshot]
    losers: list[TickerSnapshot]


class MarketOverview(BaseModel):
    provider: str
    as_of: str
    universe: list[str]
    tickers: list[TickerSnapshot]
    breadth: Breadth
    movers: Movers

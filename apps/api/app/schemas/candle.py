from datetime import datetime
from pydantic import BaseModel, Field


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[Candle]
    latest_candle_timestamp: datetime | None = None
    data_freshness: str = Field(description="FRESH | STALE | UNKNOWN")

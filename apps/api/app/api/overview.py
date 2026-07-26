"""Aggregated market overview for the dashboard page."""


import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.overview import (
    Breadth,
    MarketOverview,
    Movers,
    TickerSnapshot,
)
from app.services.market_data.factory import build_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["market-overview"])

SPARKLINE_LEN = 30
TREND_EMA_FAST = 20
TREND_EMA_SLOW = 50
# Cap simultaneous upstream requests so a 24-symbol universe (48 calls)
# doesn't burst the provider's rate limit. 8 in flight keeps the cold
# load near the latency of one symbol's fetch while staying well under
# Binance's spot weight budget.
_OVERVIEW_CONCURRENCY = 8


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _ema(vals: list[float], period: int) -> float | None:
    if not vals:
        return None
    k = 2 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _trend_from_ema(closes: list[float], last: float) -> str:
    fast = _ema(closes[-TREND_EMA_FAST:], TREND_EMA_FAST) if len(closes) >= TREND_EMA_FAST else None
    slow = _ema(closes[-TREND_EMA_SLOW:], TREND_EMA_SLOW) if len(closes) >= TREND_EMA_SLOW else None
    if fast is None or slow is None or abs(fast - slow) / last < 0.001:
        return "flat"
    return "up" if fast > slow else "down"


async def _snapshot(provider, symbol: str, sem: asyncio.Semaphore) -> TickerSnapshot | None:
    """Fetch one symbol's 1h+1d candles and fold them into a snapshot.

    Returns ``None`` (skipping the symbol) on fetch error or empty 1h
    history — same behaviour as the original serial loop, just isolated
    so the universe can be fetched concurrently.
    """
    async with sem:
        try:
            # The 1h and 1d fetches are independent — run them together.
            candles_1h, candles_1d = await asyncio.gather(
                provider.get_ohlcv(symbol, "1h", 60),
                provider.get_ohlcv(symbol, "1d", 2),
            )
        except Exception:  # noqa: BLE001
            logger.exception("overview: fetch failed for %s", symbol)
            return None

    if not candles_1h:
        return None

    closes = [c.close for c in candles_1h]
    last = closes[-1]
    trend = _trend_from_ema(closes, last)

    change_24h: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    vol_24h: float | None = None
    if candles_1d:
        today = candles_1d[-1]
        high_24h, low_24h, vol_24h = today.high, today.low, today.volume
        if today.open:
            change_24h = round((today.close - today.open) / today.open * 100, 2)

    return TickerSnapshot(
        symbol=symbol,
        last=last,
        change_24h_pct=change_24h,
        high_24h=high_24h,
        low_24h=low_24h,
        volume_24h=vol_24h,
        rsi_14=_rsi(closes),
        trend=trend,
        sparkline=closes[-SPARKLINE_LEN:],
    )


@router.get("/market-overview", response_model=MarketOverview)
async def market_overview(_user=Depends(get_current_user)):
    provider = build_provider()
    universe = list(provider.supported_symbols())

    # Fetch the whole universe concurrently (bounded) instead of one
    # symbol at a time. gather preserves order, so ``tickers`` keeps the
    # universe's ordering after we drop the skipped (None) entries.
    sem = asyncio.Semaphore(_OVERVIEW_CONCURRENCY)
    snapshots = await asyncio.gather(
        *(_snapshot(provider, symbol, sem) for symbol in universe)
    )
    tickers: list[TickerSnapshot] = [t for t in snapshots if t is not None]

    up = sum(1 for t in tickers if t.trend == "up")
    down = sum(1 for t in tickers if t.trend == "down")
    flat = len(tickers) - up - down

    by_change = sorted(
        (t for t in tickers if t.change_24h_pct is not None),
        key=lambda t: t.change_24h_pct,  # type: ignore[arg-type]
        reverse=True,
    )
    movers = Movers(
        gainers=by_change[:3],
        losers=list(reversed(by_change))[:3],
    )

    provider_name = os.getenv("MARKET_DATA_PROVIDER", "mock").lower()
    return MarketOverview(
        provider=provider_name,
        as_of=datetime.now(timezone.utc).isoformat(),
        universe=universe,
        tickers=tickers,
        breadth=Breadth(up=up, down=down, flat=flat),
        movers=movers,
    )

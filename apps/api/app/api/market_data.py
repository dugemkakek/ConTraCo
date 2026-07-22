"""HTTP/SSE routes for market data and live candle streaming."""


import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas.candle import CandleResponse
from app.db import redis_client
from app.services.market_data.factory import build_provider, build_stream
from app.services.market_data.snapshot import MarketSnapshotPipeline, SnapshotCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["market-data"])

FRESHNESS_TOLERANCE_MINUTES = {
    "1m": 5,
    "5m": 15,
    "15m": 45,
    "1h": 180,
    "4h": 720,
    "1d": 2880,
}


# NOTE: `GET /api/v1/symbols` is served exclusively by the Phase-2
# router in `app/api/symbols.py`. A legacy `{"symbols": [...]}` stub
# used to live here and shadowed that canonical endpoint because this
# module is registered first in `app/main.py`. Keep it removed.


@router.get("/market-data/{symbol}/candles", response_model=CandleResponse)
async def get_candles(
    symbol: str,
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=300, ge=1, le=1000),
):
    provider = build_provider()
    normalized_symbol = symbol.replace("-", "/").upper()

    if not provider.is_symbol_supported(normalized_symbol):
        raise HTTPException(status_code=400, detail="Unsupported symbol")
    if not provider.is_timeframe_supported(timeframe):
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    try:
        snapshot = await MarketSnapshotPipeline(
            [provider], SnapshotCache(await redis_client.get_redis())
        ).build(
            normalized_symbol, timeframe, limit=limit, categories=("ohlcv",)
        )
        candles = snapshot.candles
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("upstream fetch failed for %s %s", normalized_symbol, timeframe)
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}") from exc

    latest_ts = candles[-1].timestamp if candles else None
    freshness = "UNKNOWN"
    if latest_ts:
        age_minutes = (datetime.now(timezone.utc) - latest_ts).total_seconds() / 60
        tolerance = FRESHNESS_TOLERANCE_MINUTES.get(timeframe, 60)
        freshness = "FRESH" if age_minutes <= tolerance else "STALE"

    return CandleResponse(
        symbol=normalized_symbol,
        timeframe=timeframe,
        candles=candles,
        latest_candle_timestamp=latest_ts,
        data_freshness="STALE" if snapshot.stale_categories else freshness,
    )


@router.get("/market-data/{symbol}/stream")
async def stream_candles(
    symbol: str,
    request: Request,
    timeframe: str = Query(default="1h"),
):
    """Server-Sent Events stream of live candle updates.

    The browser opens an EventSource to this URL. The server keeps an
    upstream Gate.io WS subscription alive (deduped across all SSE
    consumers) and pipes updates down.
    """
    normalized_symbol = symbol.replace("-", "/").upper()
    stream = request.app.state.candle_stream

    if not stream._ws_subs and not stream._local_subs:  # type: ignore[attr-defined]
        # First call: actually start the upstream.
        await stream.start()

    async def event_gen():
        try:
            async for update in stream.subscribe(normalized_symbol, timeframe):
                if await request.is_disconnected():
                    break
                payload = {
                    "symbol": update.symbol,
                    "timeframe": update.timeframe,
                    "timestamp": update.candle.timestamp.isoformat(),
                    "open": update.candle.open,
                    "high": update.candle.high,
                    "low": update.candle.low,
                    "close": update.candle.close,
                    "volume": update.candle.volume,
                    "is_closed": update.is_closed,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("SSE stream error: %s", exc)
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

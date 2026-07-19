"""Gate.io spot WebSocket adapter for live candle updates.

The HTTP REST provider is fine for snapshots and history. For a real
trading terminal we want the last bar to update tick-by-tick so the
chart and the freshness badge reflect current market state.

Gate.io v4 spot WebSocket:
  URL:      wss://api.gateio.ws/ws/v4/
  Channel:  spot.candlesticks
  Subscribe payload:
    {"time": 123, "channel": "spot.candlesticks",
     "event": "subscribe", "payload": ["1m", "BTC_USDT"]}
  Update payload includes the full current candle as
    [time_s, quote_vol, close, high, low, open, base_vol]
  matching the REST format.

This module exposes a small ``CandleStream`` facade that:
  * manages one persistent WS connection
  * re-subscribes after reconnects
  * serializes updates into Redis pub/sub so multiple FastAPI workers
    can fan out to all Web/SSE clients without each opening a Gate.io
    socket.

When Redis is unavailable, ``CandleStream`` falls back to in-process
fan-out (single-worker only) so dev/test still works.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from app.schemas.candle import Candle
from app.services.market_data.gateio_rest import (
    GATEIO_INTERVALS,
    to_gateio_pair,
)

logger = logging.getLogger(__name__)

GATEIO_WS_URL = "wss://api.gateio.ws/ws/v4/"

REDIS_CANDLE_CHANNEL = "confluence:candles"


@dataclass(frozen=True)
class CandleUpdate:
    symbol: str  # slash notation, e.g. "BTC/USDT"
    timeframe: str
    candle: Candle
    is_closed: bool  # True if Gate.io says the bar has finalized


def _parse_candle_row(row: list[Any], symbol: str, timeframe: str) -> CandleUpdate:
    ts_s, _q, close, high, low, open_, _base = row
    return CandleUpdate(
        symbol=symbol,
        timeframe=timeframe,
        candle=Candle(
            timestamp=datetime.fromtimestamp(int(ts_s), tz=timezone.utc),
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(_base),
        ),
        is_closed=bool(int(time.time()) % (GATEIO_INTERVALS.get(timeframe, "1m").__len__() or 60) == 0),
    )


def _is_closed_bar(ts_s: int, timeframe: str) -> bool:
    """A bar is considered 'closed' on the producer side when the bar
    start time is older than one timeframe interval. This is a heuristic
    aligned with Gate.io's own semantics; the consumer doesn't need a
    fancier rule."""
    secs = {
        "1m": 60, "5m": 300, "15m": 900, "1h": 3600,
        "4h": 14400, "1d": 86400,
    }.get(timeframe, 60)
    return int(time.time()) >= ts_s + secs


class CandleStream:
    """Owns the upstream WS connection and fans out updates.

    Subscriptions are deduped: many consumers may ask for the same
    ``(symbol, timeframe)`` and we hold a single upstream subscription.
    """

    def __init__(self, ws_url: str = GATEIO_WS_URL, redis_client: Any | None = None):
        self._ws_url = ws_url
        self._redis = redis_client
        self._local_subs: dict[tuple[str, str], set[asyncio.Queue[CandleUpdate]]] = {}
        self._ws_subs: set[tuple[str, str]] = set()
        self._ws: Any = None
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        # Lazy in-process fan-out for when redis is absent.
        self._local_pump_task: asyncio.Task | None = None
        self._local_queue: asyncio.Queue[CandleUpdate] | None = None
        self._pubsub_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._reader_task is None:
            self._stopped.clear()
            self._reader_task = asyncio.create_task(self._run_forever())
        if self._redis is None:
            if self._local_pump_task is None:
                self._local_pump_task = asyncio.create_task(self._local_pump())
        else:
            if self._pubsub_task is None:
                self._pubsub_task = asyncio.create_task(self._pubsub_listen())

    async def stop(self) -> None:
        self._stopped.set()
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._local_pump_task is not None:
            self._local_pump_task.cancel()
            try:
                await self._local_pump_task
            except (asyncio.CancelledError, Exception):
                pass
            self._local_pump_task = None
        if self._pubsub_task is not None:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except (asyncio.CancelledError, Exception):
                pass
            self._pubsub_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None

    async def subscribe(self, symbol: str, timeframe: str) -> AsyncIterator[CandleUpdate]:
        """Async generator yielding updates for the given pair.

        Each call returns its own queue; the upstream subscription is
        shared across callers."""
        key = (symbol.upper(), timeframe)
        if timeframe not in GATEIO_INTERVALS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        queue: asyncio.Queue[CandleUpdate] = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._local_subs.setdefault(key, set()).add(queue)
            if key not in self._ws_subs:
                self._ws_subs.add(key)
                if self._ws is not None and not self._ws.closed:
                    await self._send_subscribe(key, "subscribe")
        await self.start()
        try:
            while not self._stopped.is_set():
                try:
                    yield await queue.get()
                except asyncio.CancelledError:
                    raise
        finally:
            async with self._lock:
                subs = self._local_subs.get(key)
                if subs is not None:
                    subs.discard(queue)
                    if not subs:
                        self._local_subs.pop(key, None)
                        self._ws_subs.discard(key)
                        if self._ws is not None and not self._ws.closed:
                            try:
                                await self._send_subscribe(key, "unsubscribe")
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("unsubscribe failed: %s", exc)

    async def _send_subscribe(self, key: tuple[str, str], event: str) -> None:
        symbol, timeframe = key
        payload = {
            "time": int(time.time()),
            "channel": "spot.candlesticks",
            "event": event,
            "payload": [GATEIO_INTERVALS[timeframe], to_gateio_pair(symbol)],
        }
        await self._ws.send(json.dumps(payload))

    async def _run_forever(self) -> None:
        """Reconnect loop. Backoff is bounded and jittered."""
        backoff = 1.0
        while not self._stopped.is_set():
            try:
                import websockets  # local import to keep tests light

                async with websockets.connect(self._ws_url, ping_interval=20) as ws:
                    self._ws = ws
                    backoff = 1.0
                    async with self._lock:
                        for key in list(self._ws_subs):
                            await self._send_subscribe(key, "subscribe")
                    async for raw in ws:
                        if self._stopped.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._dispatch(msg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gate.io WS loop error: %s — retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                self._ws = None

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if msg.get("channel") != "spot.candlesticks":
            return
        if msg.get("event") not in ("update", "all"):
            return
        result = msg.get("result") or {}
        # Two shapes appear in the wild:
        #  1) subscribe ack: result = {"status": "success"}
        #  2) update:         result = {"time": ts, "candles": [[...]]}
        candles = result.get("candles") or []
        if not candles:
            return
        interval = result.get("interval")
        pair = None
        # Gate.io v4 also sometimes puts the pair inside the channel field
        # of the parent message; fall back to the subscribed list.
        for (sym, tf), _ in self._local_subs.items():
            if GATEIO_INTERVALS[tf] == interval:
                pair = to_gateio_pair(sym)
                symbol, timeframe = sym, tf
                break
        if pair is None:
            return
        for row in candles:
            try:
                ts_s = int(row[0])
                update = CandleUpdate(
                    symbol=symbol,
                    timeframe=timeframe,
                    candle=Candle(
                        timestamp=datetime.fromtimestamp(ts_s, tz=timezone.utc),
                        open=float(row[5]),
                        high=float(row[3]),
                        low=float(row[4]),
                        close=float(row[2]),
                        volume=float(row[6]),
                    ),
                    is_closed=_is_closed_bar(ts_s, timeframe),
                )
            except (ValueError, TypeError, IndexError) as exc:
                logger.debug("Skipping malformed update: %r (%s)", row, exc)
                continue
            await self._broadcast(update)

    async def _broadcast(self, update: CandleUpdate) -> None:
        if self._redis is not None:
            try:
                await self._redis.publish(
                    REDIS_CANDLE_CHANNEL,
                    json.dumps(
                        {
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
                    ),
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis publish failed (%s) — using in-proc fan-out", exc)
        # in-process fallback path: the local_pump task will see it via _local_queue
        await self._enqueue_local(update)

    async def _enqueue_local(self, update: CandleUpdate) -> None:
        if self._local_queue is None:
            self._local_queue = asyncio.Queue(maxsize=4096)
        try:
            self._local_queue.put_nowait(update)
        except asyncio.QueueFull:
            logger.warning("in-proc candle queue full; dropping update")

    async def _pubsub_listen(self) -> None:
        """In a multi-worker setup we need to also receive updates
        published by *other* worker processes via Redis. The producer
        worker is the one with an active upstream WS; consumer workers
        just listen on the channel and fan out to their own SSE clients."""
        assert self._redis is not None
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(REDIS_CANDLE_CHANNEL)
            async for msg in pubsub.listen():
                if self._stopped.is_set():
                    break
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg["data"])
                    update = CandleUpdate(
                        symbol=data["symbol"],
                        timeframe=data["timeframe"],
                        candle=Candle(
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            open=float(data["open"]),
                            high=float(data["high"]),
                            low=float(data["low"]),
                            close=float(data["close"]),
                            volume=float(data["volume"]),
                        ),
                        is_closed=bool(data.get("is_closed", False)),
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    logger.debug("dropping malformed pubsub msg: %s", exc)
                    continue
                for queue in list(
                    self._local_subs.get((update.symbol, update.timeframe), set())
                ):
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        queue.put_nowait(update)
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("pubsub listener crashed: %s", exc)

    async def _local_pump(self) -> None:
        if self._local_queue is None:
            self._local_queue = asyncio.Queue(maxsize=4096)
        while not self._stopped.is_set():
            try:
                update = await self._local_queue.get()
            except asyncio.CancelledError:
                return
            for queue in list(self._local_subs.get((update.symbol, update.timeframe), set())):
                if queue.full():
                    try:
                        queue.get_nowait()  # drop oldest
                    except asyncio.QueueEmpty:
                        pass
                try:
                    queue.put_nowait(update)
                except asyncio.QueueFull:
                    pass


__all__ = [
    "CandleStream",
    "CandleUpdate",
    "GATEIO_WS_URL",
    "REDIS_CANDLE_CHANNEL",
]

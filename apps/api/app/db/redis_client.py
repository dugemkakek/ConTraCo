"""Redis client + in-process fallback.

If ``REDIS_URL`` is set and reachable, a real ``redis.asyncio.Redis``
client is returned. Otherwise a tiny in-memory pub/sub shim with the
same ``publish``/``subscribe``/``ping`` surface is returned. This keeps
the app runnable on a developer machine with no Redis available, and
keeps the dependency injection uniform in both modes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

_client: Any | None = None
_mode: str = "unset"


class _InProcChannel:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[str]] = []
        self._lock = asyncio.Lock()

    async def publish(self, message: str) -> int:
        async with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass
        return len(subs)

    async def listen(self) -> AsyncIterator[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


class _InProcClient:
    """Drop-in subset of redis.asyncio.Redis — only what we use."""

    def __init__(self) -> None:
        self._channels: dict[str, _InProcChannel] = {}
        self._lock = asyncio.Lock()

    async def _channel(self, name: str) -> _InProcChannel:
        async with self._lock:
            ch = self._channels.get(name)
            if ch is None:
                ch = _InProcChannel()
                self._channels[name] = ch
            return ch

    async def publish(self, channel: str, message: str) -> int:
        return await (await self._channel(channel)).publish(message)

    def pubsub(self) -> "_InProcPubSub":
        return _InProcPubSub(self)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:  # noqa: D401
        return None


class _InProcPubSub:
    def __init__(self, client: _InProcClient) -> None:
        self._client = client
        self._channel_name: str | None = None
        self._gen: AsyncIterator[str] | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel_name = channel

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        if self._channel_name is None:
            return
        ch = await self._client._channel(self._channel_name)  # noqa: SLF001
        async for message in ch.listen():
            yield {"type": "message", "channel": self._channel_name, "data": message}

    async def close(self) -> None:
        return None


async def get_redis() -> Any:
    global _client, _mode
    if _client is not None:
        return _client

    import os

    url = os.getenv("REDIS_URL")
    if url:
        try:
            import redis.asyncio as redis_async  # type: ignore[import-not-found]

            client = redis_async.from_url(url, decode_responses=True)
            await client.ping()
            _client = client
            _mode = "redis"
            logger.info("Using real Redis at %s", url)
            return _client
        except Exception as exc:  # noqa: BLE001
            logger.warning("REDIS_URL set but unreachable (%s) — falling back to in-proc", exc)

    _client = _InProcClient()
    _mode = "inproc"
    logger.info("Using in-process pub/sub shim (no Redis configured)")
    return _client


def mode() -> str:
    return _mode


async def aclose() -> None:
    global _client
    if _client is not None and hasattr(_client, "aclose"):
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            pass
    _client = None


__all__ = ["get_redis", "mode", "aclose"]

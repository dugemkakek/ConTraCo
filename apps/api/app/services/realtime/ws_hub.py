"""WebSocket connection manager — hub for real-time events."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections per user for real-time updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._symbol_subscriptions: dict[str, set[str]] = {}  # symbol -> user_ids

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)
        logger.info("WS connected: user=%s (%d connections)", user_id, len(self.active_connections[user_id]))

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [ws for ws in self.active_connections[user_id] if ws != websocket]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast_to_user(self, user_id: str, event: dict[str, Any]):
        dead: list[WebSocket] = []
        for conn in self.active_connections.get(user_id, []):
            try:
                await conn.send_json(event)
            except Exception:  # noqa: BLE001
                dead.append(conn)
        for d in dead:
            self.disconnect(d, user_id)

    async def broadcast_symbol_update(self, symbol: str, data: dict[str, Any]):
        """Broadcast to all users subscribed to this symbol."""
        user_ids = self._symbol_subscriptions.get(symbol, set())
        for uid in user_ids:
            await self.broadcast_to_user(uid, {"type": "candle_update", "symbol": symbol, **data})

    def subscribe_symbol(self, user_id: str, symbol: str):
        self._symbol_subscriptions.setdefault(symbol, set()).add(user_id)

    def unsubscribe_symbol(self, user_id: str, symbol: str):
        if symbol in self._symbol_subscriptions:
            self._symbol_subscriptions[symbol].discard(user_id)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "users": len(self.active_connections),
            "connections": sum(len(v) for v in self.active_connections.values()),
            "symbol_subscriptions": {s: len(u) for s, u in self._symbol_subscriptions.items()},
        }


# Global singleton
manager = ConnectionManager()

"""FastAPI application entry point.

Lifespan responsibilities:
  * load ``apps/api/.env`` into ``os.environ`` (no-op if the file is
    missing — Docker and explicit-launch paths already pass env vars)
  * run ``alembic upgrade head`` in dev so a fresh checkout gets a
    usable schema without a separate command
  * bring up the Redis client (real or in-proc shim)
  * construct the configured market data provider and live candle
    stream and stash them on ``app.state``
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _load_local_dotenv() -> None:
    """Best-effort ``apps/api/.env`` loader.

    We don't make ``python-dotenv`` a hard requirement, so we import it
    lazily and silently skip when it's not installed. The Docker image
    has it via ``uvicorn[standard]``; the local venv we just built
    might not. Either way the bot is runnable.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(env_path, override=False)
        logger.info("loaded %s", env_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("dotenv load skipped: %s", exc)

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.journal import router as journal_router
from app.api.market_data import router as market_data_router
from app.api.scanner import router as scanner_router
from app.api.strategy import router as strategy_router
from app.api.symbols import router as symbols_router
from app.api.trades import router as trades_router
from app.api.overview import router as overview_router
from app.api.fundamentals import router as fundamentals_router
from app.api.orderbook import router as orderbook_router
from app.api.alerts import router as alerts_router
from app.services.realtime.ws_hub import manager as ws_manager
from app.api.analytics import router as analytics_router
from app.api.aggregate import router as aggregate_router
from app.db import redis_client
from app.services.llm import current_provider
from app.services.market_data.factory import build_stream

logger = logging.getLogger(__name__)


def _split_cors_origins(raw: str | None) -> list[str]:
    if not raw or raw.strip() in {"", "*"}:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _maybe_run_migrations() -> None:
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "1") != "1":
        return
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite"):
        # For SQLite (dev/CI without a Postgres container) we don't
        # have an alembic SQLite configuration, so fall back to
        # ``Base.metadata.create_all`` so the file-backed DB has a
        # usable schema on first boot.
        from app.db.models import Base
        from app.db import get_engine

        Base.metadata.create_all(get_engine())
        logger.info("sqlite schema: created")
        return
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        command.upgrade(cfg, "head")
        logger.info("alembic upgrade head: ok")
    except Exception as exc:  # noqa: BLE001
        logger.warning("alembic upgrade failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_local_dotenv()
    _maybe_run_migrations()
    redis = await redis_client.get_redis()
    app.state.redis = redis
    app.state.candle_stream = build_stream(redis_client=redis)
    try:
        yield
    finally:
        try:
            await app.state.candle_stream.stop()
        except Exception:  # noqa: BLE001
            pass
        await redis_client.aclose()


app = FastAPI(
    title="Confluence Trading Consultant API",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_split_cors_origins(os.getenv("CORS_ORIGINS")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data_router)
app.include_router(auth_router)
app.include_router(strategy_router)
app.include_router(analysis_router)
app.include_router(symbols_router)
app.include_router(scanner_router)
app.include_router(journal_router)
app.include_router(trades_router)
app.include_router(overview_router)
app.include_router(fundamentals_router)
app.include_router(orderbook_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(aggregate_router)


@app.get("/health")
async def health():
    provider = current_provider()
    return {
        "status": "ok",
        "redis_mode": redis_client.mode(),
        "market_data_provider": os.getenv("MARKET_DATA_PROVIDER", "mock"),
        "llm_provider": provider["llm_provider"],
        "llm_model": provider["llm_model"],
    }


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """WebSocket endpoint for real-time updates (candle, alert, scanner, analysis)."""
    from app.security import decode_token
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=4001)
        return
    user_id = str(payload["sub"])
    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "subscribe" and data.get("symbol"):
                ws_manager.subscribe_symbol(user_id, data["symbol"])
                await ws_manager.broadcast_to_user(user_id, {
                    "type": "subscribed", "symbol": data["symbol"],
                })
            elif data.get("type") == "unsubscribe" and data.get("symbol"):
                ws_manager.unsubscribe_symbol(user_id, data["symbol"])
    except Exception:  # noqa: BLE001
        pass
    finally:
        ws_manager.disconnect(websocket, user_id)

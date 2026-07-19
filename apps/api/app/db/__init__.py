"""Database engine + session factory.

Two flavors:
  * ``engine`` is created lazily on first use; tests can override by
    calling ``set_engine``.
  * ``get_db`` is a FastAPI dependency that yields a SQLAlchemy Session.

The ``DATABASE_URL`` env var is honored; in test runs (CI / no Postgres)
a SQLite URL is used automatically.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


class _LazySessionLocal:
    """Property that returns a working sessionmaker even if accessed
    before the engine has been created (e.g. from a background task)."""

    def __call__(self) -> sessionmaker[Session]:
        global _SessionLocal
        if _SessionLocal is None:
            get_engine()
        assert _SessionLocal is not None
        return _SessionLocal


SessionLocal = _LazySessionLocal()


def _resolve_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Fall back to a per-process SQLite file in the api dir; perfect for
    # local dev without a Postgres container.
    return "sqlite:///./confluence.db"


def _make_engine() -> Engine:
    url = _resolve_url()
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, future=True, connect_args=connect_args, pool_pre_ping=True)
    return engine


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _make_engine()
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _engine


def set_engine(engine: Engine) -> None:
    """Tests use this to inject a pre-built engine (typically in-memory SQLite)."""
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["get_engine", "get_db", "set_engine"]

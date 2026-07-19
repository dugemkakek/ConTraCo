"""Pytest fixtures.

Tests run against an isolated in-memory SQLite DB. The test session
fixture builds the schema via ``Base.metadata.create_all`` so test
isolation is independent of alembic/Postgres availability.
"""

from __future__ import annotations

import os
import shutil
from typing import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("MARKET_DATA_PROVIDER", "mock")
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "0")

# Clear all .pyc caches before importing app modules. Without this,
# edits made during a long dev session would silently take effect only
# after Python's bytecode-mtime check invalidated the cache — and
# sometimes that check races with editors and test runs, leaving
# stale .pyc files that override the current .py source.
_app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _root, _dirs, _files in os.walk(_app_root):
    for _d in list(_dirs):
        if _d == "__pycache__":
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)
            _dirs.remove(_d)
    for _f in _files:
        if _f.endswith(".pyc"):
            try:
                os.remove(os.path.join(_root, _f))
            except OSError:
                pass

from app.db import get_db, set_engine  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.redis_client import aclose as redis_aclose  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    set_engine(engine)
    Base.metadata.create_all(engine)
    yield
    await redis_aclose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Direct DB session for tests that need to inspect persistence."""
    from app.db import get_db  # noqa: PLC0415

    gen = get_db()
    session = next(gen)
    try:
        yield session
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

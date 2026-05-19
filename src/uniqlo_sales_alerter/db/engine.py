"""Async engine, session factory, and health probe for the SQLite store.

The database path is resolvable from the ``ALERTER_DB_PATH`` environment
variable (default ``/app/data/alerter.db``). The engine is module-level so
that FastAPI dependencies and lifespan callbacks share a single connection
pool.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "/app/data/alerter.db"


def resolve_db_path() -> Path:
    """Return the absolute path to the SQLite database file."""
    return Path(os.environ.get("ALERTER_DB_PATH", _DEFAULT_DB_PATH))


def _build_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


DATABASE_URL: str = _build_url(resolve_db_path())

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=False,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an ``AsyncSession`` and commits on exit."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def health_probe() -> bool:
    """Insert and delete a row in the dedicated ``_health_probe`` table.

    Returns ``True`` on success, ``False`` on any exception. The exception is
    logged but not re-raised — the caller decides whether to fail the response.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO _health_probe DEFAULT VALUES"))
            await conn.execute(text("DELETE FROM _health_probe"))
        return True
    except Exception as exc:
        logger.warning("Health probe write failed: %s", exc)
        return False

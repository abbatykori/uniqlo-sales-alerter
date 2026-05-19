"""Apply Alembic migrations programmatically at app startup.

Runs ``alembic upgrade head`` against the configured database. Idempotent —
does nothing when the database is already at head. Used by the FastAPI
lifespan so the container does not need a separate entrypoint command for
schema management. Constructs the Alembic ``Config`` in Python so it works
both from a source checkout and from an installed wheel where ``alembic.ini``
may not be present on disk.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _build_alembic_config() -> Config:
    if not _MIGRATIONS_DIR.exists():
        raise FileNotFoundError(
            f"Alembic migrations directory not found at {_MIGRATIONS_DIR}"
        )
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def upgrade_to_head() -> None:
    """Synchronously apply migrations to head — usable from tests and CLI."""
    command.upgrade(_build_alembic_config(), "head")


async def ensure_schema() -> None:
    """Run ``alembic upgrade head`` in a thread; safe to call multiple times."""
    logger.info("Applying database migrations")
    await asyncio.to_thread(upgrade_to_head)
    logger.info("Database migrations applied")

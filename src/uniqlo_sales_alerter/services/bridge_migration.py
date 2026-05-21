"""One-shot bridge migration: legacy ``config.yaml::filters`` → ``saved_filters`` row.

Runs once per installation, idempotent via a row in ``migrations_applied``
named ``bridge_v1``. If the user has tuned any field on the legacy single
global filter (gender / min_sale_percentage / sizes / ignored_keywords),
seed a corresponding ``saved_filters`` row named ``"Imported"`` so the
matcher has something to match against on first run. Default-shaped
configs skip the seed — the user can add filters via ``/ui/filters`` or
the REST API.

Watched products, ignored products, and global ignored keywords are NOT
copied here. They stay on ``config.yaml`` until the step-15 full upstream
migration moves them into their SQLite tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uniqlo_sales_alerter.db.models import MigrationApplied, SavedFilter

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import AppConfig, FilterConfig

logger = logging.getLogger(__name__)

_BRIDGE_MARKER = "bridge_v1"


def _legacy_is_default(f: FilterConfig) -> bool:
    """True when the legacy filter block looks like the ``FilterConfig`` defaults.

    ``FilterConfig`` defaults are ``gender=["men","women"]``, ``min_sale_percentage=50.0``,
    empty size lists, ``one_size=False``, and no ``ignored_keywords``. If the
    user has tuned any of these we treat the filter as user-intended and
    seed a saved-filter row from it.
    """
    return (
        sorted(g.lower() for g in f.gender) == ["men", "women"]
        and f.min_sale_percentage == 50.0
        and not f.sizes.clothing
        and not f.sizes.pants
        and not f.sizes.shoes
        and not f.sizes.one_size
        and not f.ignored_keywords
    )


async def _has_marker(session: AsyncSession) -> bool:
    row = await session.get(MigrationApplied, _BRIDGE_MARKER)
    return row is not None


async def _saved_filter_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(SavedFilter.id)))
    return int(result.scalar_one())


def _build_imported_row(f: FilterConfig) -> SavedFilter:
    return SavedFilter(
        name="Imported",
        gender=[g.lower() for g in f.gender],
        min_discount=f.min_sale_percentage,
        sizes_clothing=list(f.sizes.clothing),
        sizes_pants=list(f.sizes.pants),
        sizes_shoes=list(f.sizes.shoes),
        one_size_match=1 if f.sizes.one_size else 0,
        availability_mode="both",
        ignored_keywords=list(f.ignored_keywords),
        enabled=1,
    )


async def ensure_bridge_migration(session: AsyncSession, config: AppConfig) -> None:
    """Idempotently seed a saved filter from ``config.filters`` on first run.

    Four branches:

    1. Marker already present → no-op.
    2. ``saved_filters`` already has rows → mark and skip (user has filters).
    3. Legacy ``config.filters`` is default-shaped → mark and skip (no seed needed).
    4. Otherwise → insert one ``Imported`` row and write the marker.

    All branches commit together via the caller's transaction context.
    """
    if await _has_marker(session):
        return

    if await _saved_filter_count(session) > 0:
        session.add(MigrationApplied(name=_BRIDGE_MARKER))
        await session.flush()
        logger.info("Bridge migration: saved_filters already populated; marker recorded")
        return

    if _legacy_is_default(config.filters):
        session.add(MigrationApplied(name=_BRIDGE_MARKER))
        await session.flush()
        logger.info("Bridge migration: legacy config matches defaults; nothing to seed")
        return

    session.add(_build_imported_row(config.filters))
    session.add(MigrationApplied(name=_BRIDGE_MARKER))
    await session.flush()
    logger.info("Bridge migration: seeded 'Imported' filter from legacy config")

"""One-shot upstream-config migration.

The pre-fork ``kequach/uniqlo-sales-alerter`` (and its descendents like
``jabescript``) persists three things on disk:

1. ``config.yaml`` — a ``filters:`` block with ``watched_urls`` /
   ``watched_variants`` / ``ignored_products`` / ``ignored_keywords``
2. ``.seen_variants.json`` — the new-deal-detection state

After step 8 (saved-filter matcher) and step 15 (this module), those
should live in the SQLite tables. The :func:`ensure_upstream_migration`
function imports them, then moves the source files to
``data/migrated/<ISO timestamp>/`` so the user has a recoverable backup.

Idempotent via the ``migrations_applied`` row ``upstream_v1``. Atomic at
the SQL transaction level: a partial parse failure rolls back the inserts
and leaves the source files untouched, so the next boot re-attempts.

Bridge migration (step 8 PR-5) already seeded a saved_filter from
``config.filters`` (gender/min_discount/sizes). This module is
complementary: it imports the *other* parts of the legacy config
(watched/ignored) plus the JSON state file.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from uniqlo_sales_alerter.db.models import (
    IgnoredKeyword,
    IgnoredProduct,
    MigrationApplied,
    SeenVariant,
    WatchedVariant,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from uniqlo_sales_alerter.config import AppConfig

logger = logging.getLogger(__name__)

_MARKER = "upstream_v1"


def _migrated_dir(data_root: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return data_root / "migrated" / ts


def _resolve_seen_variants_path(data_root: Path) -> Path | None:
    """Locate the upstream ``.seen_variants.json`` file, if any."""
    candidates = [
        data_root / ".seen_variants.json",
        data_root.parent / ".seen_variants.json",  # /app/.seen_variants.json
        Path("/app/.seen_variants.json"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


async def _has_marker(session: AsyncSession) -> bool:
    row = await session.get(MigrationApplied, _MARKER)
    return row is not None


async def _import_watched_variants(
    session: AsyncSession, config: AppConfig
) -> int:
    """Copy ``config.filters.watched_variants`` into the SQLite table."""
    existing_keys = set(
        (await session.execute(
            select(
                WatchedVariant.product_id,
                WatchedVariant.color_code,
                WatchedVariant.size_code,
            )
        )).all()
    )
    inserted = 0
    for wv in config.filters.watched_variants:
        if not (wv.id and wv.color and wv.size):
            continue
        key = (wv.id, wv.color, wv.size)
        if key in existing_keys:
            continue
        session.add(WatchedVariant(
            product_id=wv.id, color_code=wv.color, size_code=wv.size,
        ))
        existing_keys.add(key)
        inserted += 1
    if inserted:
        await session.flush()
    return inserted


async def _import_ignored_products(
    session: AsyncSession, config: AppConfig
) -> int:
    """Copy ``config.filters.ignored_products`` into the SQLite table."""
    existing = {
        pid for (pid,) in (await session.execute(
            select(IgnoredProduct.product_id)
        )).all()
    }
    inserted = 0
    for ip in config.filters.ignored_products:
        if not ip.id or ip.id in existing:
            continue
        session.add(IgnoredProduct(product_id=ip.id, name=ip.name or None))
        existing.add(ip.id)
        inserted += 1
    if inserted:
        await session.flush()
    return inserted


async def _import_ignored_keywords(
    session: AsyncSession, config: AppConfig
) -> int:
    """Copy ``config.filters.ignored_keywords`` into the SQLite table."""
    existing = {
        kw.lower() for (kw,) in (await session.execute(
            select(IgnoredKeyword.keyword)
        )).all()
    }
    inserted = 0
    for keyword in config.filters.ignored_keywords:
        cleaned = keyword.strip()
        if not cleaned or cleaned.lower() in existing:
            continue
        session.add(IgnoredKeyword(keyword=cleaned))
        existing.add(cleaned.lower())
        inserted += 1
    if inserted:
        await session.flush()
    return inserted


async def _import_seen_variants(
    session: AsyncSession, seen_path: Path | None,
) -> int:
    """Parse ``.seen_variants.json`` and write to the ``seen_variants`` table."""
    if seen_path is None:
        return 0
    try:
        data = json.loads(seen_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping seen_variants import — %s", exc)
        return 0

    variants = data.get("variants", []) if isinstance(data, dict) else data
    if not isinstance(variants, list):
        logger.warning("Skipping seen_variants import — unexpected JSON shape")
        return 0

    existing = {
        key for (key,) in (await session.execute(
            select(SeenVariant.variant_key)
        )).all()
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    inserted = 0
    for key in variants:
        if not isinstance(key, str) or not key or key in existing:
            continue
        parts = key.split(":")
        product_id = parts[0] if parts else ""
        color = parts[1] if len(parts) > 1 else ""
        size = parts[2] if len(parts) > 2 else ""
        suffix = parts[3] if len(parts) > 3 else ""
        try:
            discount: float | None = float(suffix)
        except ValueError:
            discount = None
        session.add(SeenVariant(
            variant_key=key,
            product_id=product_id,
            color_code=color,
            size_code=size,
            discount_pct=discount,
            last_seen_at=now,
        ))
        existing.add(key)
        inserted += 1
    if inserted:
        await session.flush()
    return inserted


def _move_source_files(
    data_root: Path, seen_path: Path | None, config_path: Path | None
) -> Path | None:
    """Move source files to ``data/migrated/<ts>/``. Never deletes the originals."""
    files_to_move = [p for p in (seen_path, config_path) if p is not None and p.exists()]
    if not files_to_move:
        return None
    target = _migrated_dir(data_root)
    target.mkdir(parents=True, exist_ok=True)
    for src in files_to_move:
        try:
            shutil.move(str(src), target / src.name)
            logger.info("Moved %s to %s", src, target)
        except Exception:
            logger.exception("Failed to move %s", src)
    return target


async def ensure_upstream_migration(
    session: AsyncSession,
    config: AppConfig,
    *,
    data_root: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, int]:
    """Import upstream config + seen-variant state once per install.

    Returns a dict of counts ``{watched, ignored_products, ignored_keywords,
    seen_variants}`` for logging. No-op when the marker is already present.

    *data_root* defaults to ``/app/data`` (matches the runtime volume mount).
    *config_path* is the source ``config.yaml`` (default ``/app/config.yaml``);
    moved to the migrated directory if present.
    """
    counts: dict[str, int] = dict(
        watched=0, ignored_products=0, ignored_keywords=0, seen_variants=0,
    )

    if await _has_marker(session):
        return counts

    data_root = data_root or Path("/app/data")
    config_path = config_path or Path("/app/config.yaml")
    seen_path = _resolve_seen_variants_path(data_root)

    counts["watched"] = await _import_watched_variants(session, config)
    counts["ignored_products"] = await _import_ignored_products(session, config)
    counts["ignored_keywords"] = await _import_ignored_keywords(session, config)
    counts["seen_variants"] = await _import_seen_variants(session, seen_path)

    session.add(MigrationApplied(name=_MARKER))
    await session.flush()

    # Source file move happens AFTER SQL commit; failure here doesn't undo
    # the import (idempotent on next boot via the marker).
    moved_to = _move_source_files(
        data_root,
        seen_path,
        config_path if config_path.exists() else None,
    )
    if moved_to:
        logger.info(
            "Upstream migration complete: %s — source files moved to %s",
            counts, moved_to,
        )
    else:
        logger.info("Upstream migration complete: %s (no source files moved)", counts)

    return counts

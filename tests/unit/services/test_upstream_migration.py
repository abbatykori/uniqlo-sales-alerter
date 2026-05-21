"""Upstream config migration: import + idempotency + source-file move."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select, text

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import (
    IgnoredKeyword,
    IgnoredProduct,
    MigrationApplied,
    SeenVariant,
    WatchedVariant,
)
from uniqlo_sales_alerter.services.upstream_migration import (
    _MARKER,
    ensure_upstream_migration,
)


@pytest.fixture(autouse=True)
def _clean_tables():
    async def _truncate():
        async with engine.begin() as conn:
            for table in (
                "watched_variants",
                "ignored_products",
                "ignored_keywords",
                "seen_variants",
                "migrations_applied",
            ):
                await conn.execute(text(f"DELETE FROM {table}"))

    asyncio.run(_truncate())
    yield


async def _run(config: AppConfig, *, tmp_path, with_seen: list[str] | None = None):
    seen_path = tmp_path / ".seen_variants.json"
    if with_seen is not None:
        seen_path.write_text(json.dumps({"variants": with_seen}))
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("uniqlo: {country: 'nl/nl'}\n")
    async with async_session_factory() as session:
        async with session.begin():
            counts = await ensure_upstream_migration(
                session, config,
                data_root=tmp_path,
                config_path=config_yaml,
            )
    return counts, seen_path, config_yaml


@pytest.mark.asyncio
async def test_imports_watched_variants(tmp_path):
    config = AppConfig.model_validate({
        "filters": {
            "watched_variants": [
                {"id": "E001", "color": "09", "size": "002", "name": "Black M"},
                {"id": "E002", "color": "00", "size": "001", "name": "Beige S"},
            ],
        },
    })
    counts, _, _ = await _run(config, tmp_path=tmp_path)
    assert counts["watched"] == 2

    async with async_session_factory() as session:
        rows = (await session.execute(select(WatchedVariant))).scalars().all()
    pids = sorted(r.product_id for r in rows)
    assert pids == ["E001", "E002"]


@pytest.mark.asyncio
async def test_imports_ignored_products_and_keywords(tmp_path):
    config = AppConfig.model_validate({
        "filters": {
            "ignored_products": [
                {"id": "E777", "name": "Boring Coat"},
                {"id": "E888"},
            ],
            "ignored_keywords": ["scarf", "Glove", "scarf"],
        },
    })
    counts, _, _ = await _run(config, tmp_path=tmp_path)
    assert counts["ignored_products"] == 2
    assert counts["ignored_keywords"] == 2  # "scarf" dedup case-insensitive

    async with async_session_factory() as session:
        ip_rows = (await session.execute(select(IgnoredProduct))).scalars().all()
        kw_rows = (await session.execute(select(IgnoredKeyword))).scalars().all()
    assert sorted(r.product_id for r in ip_rows) == ["E777", "E888"]
    assert sorted(r.keyword.lower() for r in kw_rows) == ["glove", "scarf"]


@pytest.mark.asyncio
async def test_imports_seen_variants_json(tmp_path):
    config = AppConfig()
    counts, _, _ = await _run(
        config, tmp_path=tmp_path,
        with_seen=["E001:09:002:50", "E002:00:001:30.5", "E003:00:001:sale"],
    )
    assert counts["seen_variants"] == 3

    async with async_session_factory() as session:
        rows = (await session.execute(select(SeenVariant))).scalars().all()
    by_key = {r.variant_key: r for r in rows}
    assert by_key["E001:09:002:50"].discount_pct == 50.0
    assert by_key["E002:00:001:30.5"].discount_pct == 30.5
    assert by_key["E003:00:001:sale"].discount_pct is None


@pytest.mark.asyncio
async def test_writes_marker_row(tmp_path):
    config = AppConfig()
    await _run(config, tmp_path=tmp_path)
    async with async_session_factory() as session:
        marker = await session.get(MigrationApplied, _MARKER)
    assert marker is not None


@pytest.mark.asyncio
async def test_idempotent_second_run_no_op(tmp_path):
    config = AppConfig.model_validate({
        "filters": {
            "watched_variants": [
                {"id": "E001", "color": "09", "size": "002", "name": "X"},
            ],
        },
    })
    counts1, _, _ = await _run(config, tmp_path=tmp_path)
    counts2, _, _ = await _run(config, tmp_path=tmp_path)
    assert counts1["watched"] == 1
    assert counts2 == {
        "watched": 0,
        "ignored_products": 0,
        "ignored_keywords": 0,
        "seen_variants": 0,
    }


@pytest.mark.asyncio
async def test_moves_source_files_to_migrated_dir(tmp_path):
    config = AppConfig()
    counts, seen_path, config_path = await _run(
        config, tmp_path=tmp_path, with_seen=["E001:09:002:40"],
    )
    assert not seen_path.exists()
    assert not config_path.exists()

    # data/migrated/<timestamp>/ contains both files
    migrated = list((tmp_path / "migrated").iterdir())
    assert len(migrated) == 1
    contents = sorted(p.name for p in migrated[0].iterdir())
    assert ".seen_variants.json" in contents
    assert "config.yaml" in contents


@pytest.mark.asyncio
async def test_corrupt_seen_variants_json_does_not_raise(tmp_path):
    config = AppConfig()
    seen = tmp_path / ".seen_variants.json"
    seen.write_text("not json")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("uniqlo: {country: 'nl/nl'}\n")
    async with async_session_factory() as session:
        async with session.begin():
            counts = await ensure_upstream_migration(
                session, config, data_root=tmp_path, config_path=cfg,
            )
    assert counts["seen_variants"] == 0
    # Marker should still be written (the import was best-effort and the
    # config side succeeded)
    async with async_session_factory() as session:
        assert await session.get(MigrationApplied, _MARKER) is not None


@pytest.mark.asyncio
async def test_no_seen_file_is_handled(tmp_path):
    config = AppConfig.model_validate({
        "filters": {
            "watched_variants": [
                {"id": "E001", "color": "09", "size": "002", "name": "X"},
            ],
        },
    })
    counts, _, _ = await _run(config, tmp_path=tmp_path, with_seen=None)
    # No JSON file present
    assert counts["seen_variants"] == 0
    assert counts["watched"] == 1


@pytest.mark.asyncio
async def test_duplicate_watched_entry_only_inserts_once(tmp_path):
    """Two identical watched_variants in config (legacy mishap) → one row."""
    config = AppConfig.model_validate({
        "filters": {
            "watched_variants": [
                {"id": "E001", "color": "09", "size": "002", "name": "X"},
                {"id": "E001", "color": "09", "size": "002", "name": "X duplicate"},
            ],
        },
    })
    counts, _, _ = await _run(config, tmp_path=tmp_path)
    assert counts["watched"] == 1

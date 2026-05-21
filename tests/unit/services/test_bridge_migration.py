"""Bridge migration — four branches of ensure_bridge_migration."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import MigrationApplied, SavedFilter
from uniqlo_sales_alerter.services.bridge_migration import (
    _BRIDGE_MARKER,
    ensure_bridge_migration,
)


@pytest.fixture(autouse=True)
def _clean_marker():
    """Drop the bridge marker before each test so we can test each branch fresh."""
    import asyncio

    from sqlalchemy import text

    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM migrations_applied WHERE name=:n"),
                               {"n": _BRIDGE_MARKER})

    asyncio.run(_truncate())
    yield


async def _saved_filter_names() -> list[str]:
    async with async_session_factory() as session:
        rows = (await session.execute(select(SavedFilter.name))).scalars().all()
    return list(rows)


async def _marker_exists() -> bool:
    async with async_session_factory() as session:
        return await session.get(MigrationApplied, _BRIDGE_MARKER) is not None


@pytest.mark.asyncio
async def test_seeds_imported_filter_for_non_default_config() -> None:
    config = AppConfig.model_validate({
        "uniqlo": {"country": "nl/nl"},
        "filters": {
            "gender": ["men"],
            "min_sale_percentage": 70.0,
            "sizes": {"clothing": ["XXL"]},
        },
    })
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config)

    assert "Imported" in await _saved_filter_names()
    assert await _marker_exists()


@pytest.mark.asyncio
async def test_default_shaped_config_does_not_seed() -> None:
    config = AppConfig()  # ships defaults
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config)

    assert await _saved_filter_names() == []
    assert await _marker_exists()


@pytest.mark.asyncio
async def test_skips_when_saved_filters_already_populated() -> None:
    # Pre-seed a user-created filter; the bridge should NOT add Imported.
    async with async_session_factory() as session:
        async with session.begin():
            session.add(SavedFilter(
                name="UserMade",
                gender=["men"],
                min_discount=40,
                sizes_clothing=[], sizes_pants=[], sizes_shoes=[],
                one_size_match=0, availability_mode="both",
                ignored_keywords=[], enabled=1,
            ))

    config = AppConfig.model_validate({
        "filters": {"gender": ["men"], "min_sale_percentage": 70.0},
    })
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config)

    names = await _saved_filter_names()
    assert "UserMade" in names
    assert "Imported" not in names
    assert await _marker_exists()


@pytest.mark.asyncio
async def test_idempotent_when_marker_already_present() -> None:
    """A second call after a successful first run does nothing — even if config changed."""
    config1 = AppConfig.model_validate({
        "filters": {"gender": ["men"], "min_sale_percentage": 70.0},
    })
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config1)
    assert "Imported" in await _saved_filter_names()

    # Change the config and call again — must NOT add another row.
    config2 = AppConfig.model_validate({
        "filters": {"gender": ["women"], "min_sale_percentage": 80.0},
    })
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config2)

    names = await _saved_filter_names()
    assert names.count("Imported") == 1


@pytest.mark.asyncio
async def test_seeds_with_legacy_field_translation() -> None:
    """gender goes lowercase, min_sale_percentage → min_discount, sizes copy across."""
    config = AppConfig.model_validate({
        "filters": {
            "gender": ["MEN", "Women"],
            "min_sale_percentage": 60.0,
            "sizes": {
                "clothing": ["M", "L"],
                "pants": ["32inch"],
                "one_size": True,
            },
            "ignored_keywords": ["jacket"],
        },
    })
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config)

    async with async_session_factory() as session:
        row = (await session.execute(select(SavedFilter))).scalar_one()

    assert row.name == "Imported"
    assert sorted(row.gender) == ["men", "women"]
    assert row.min_discount == 60.0
    assert row.sizes_clothing == ["M", "L"]
    assert row.sizes_pants == ["32inch"]
    assert row.one_size_match == 1
    assert row.ignored_keywords == ["jacket"]
    assert row.availability_mode == "both"
    assert row.enabled == 1

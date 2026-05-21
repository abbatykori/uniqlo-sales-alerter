"""SQLite-backed SeenVariantStore — round-trip, column parsing, pruning."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import SeenVariant
from uniqlo_sales_alerter.services.state import SeenVariantStore


@pytest.fixture(autouse=True)
def _clean_seen_variants():
    """Reset the seen_variants table between tests for deterministic state."""

    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM seen_variants"))

    asyncio.run(_truncate())
    yield


@pytest.fixture()
def store() -> SeenVariantStore:
    return SeenVariantStore(async_session_factory)


@pytest.mark.asyncio
async def test_save_then_load_round_trip(store: SeenVariantStore) -> None:
    keys = {"E001:09:004:50", "E002:00:001:sale"}
    await store.save(keys)
    loaded = await store.load()
    assert loaded == keys


@pytest.mark.asyncio
async def test_save_parses_variant_key_into_columns(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50.2"})
    async with async_session_factory() as session:
        row = (await session.execute(select(SeenVariant))).scalar_one()
    assert row.variant_key == "E001:09:004:50.2"
    assert row.product_id == "E001"
    assert row.color_code == "09"
    assert row.size_code == "004"
    assert row.discount_pct == pytest.approx(50.2)


@pytest.mark.asyncio
async def test_save_handles_sale_suffix_with_null_discount(store: SeenVariantStore) -> None:
    await store.save({"E777:00:002:sale"})
    async with async_session_factory() as session:
        row = (await session.execute(select(SeenVariant))).scalar_one()
    assert row.discount_pct is None
    assert row.color_code == "00"
    assert row.size_code == "002"


@pytest.mark.asyncio
async def test_save_deletes_missing_keys(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50", "E002:00:001:30"})
    assert await store.load() == {"E001:09:004:50", "E002:00:001:30"}

    await store.save({"E002:00:001:30"})  # E001 dropped
    assert await store.load() == {"E002:00:001:30"}


@pytest.mark.asyncio
async def test_save_empty_set_deletes_all(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50"})
    await store.save(set())
    assert await store.load() == set()


@pytest.mark.asyncio
async def test_save_upsert_updates_last_seen_at(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50"})
    async with async_session_factory() as session:
        first = (await session.execute(select(SeenVariant))).scalar_one()
        first_ts = first.last_seen_at
    # Re-save: row stays, timestamp updates.
    await store.save({"E001:09:004:50"})
    async with async_session_factory() as session:
        again = (await session.execute(select(SeenVariant))).scalar_one()
    assert again.last_seen_at >= first_ts


@pytest.mark.asyncio
async def test_prune_older_than(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50", "E002:00:001:30"})
    # Hand-age one row.
    long_ago = datetime.now(timezone.utc) - timedelta(days=400)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE seen_variants SET last_seen_at = :ts WHERE variant_key = :k"),
            {"ts": long_ago, "k": "E001:09:004:50"},
        )
    deleted = await store.prune_older_than(days=365)
    assert deleted == 1
    assert await store.load() == {"E002:00:001:30"}


@pytest.mark.asyncio
async def test_prune_returns_zero_when_nothing_old(store: SeenVariantStore) -> None:
    await store.save({"E001:09:004:50"})
    deleted = await store.prune_older_than(days=365)
    assert deleted == 0
    assert await store.load() == {"E001:09:004:50"}

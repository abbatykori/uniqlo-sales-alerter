"""``enabled`` is derived from data presence — not from an explicit form field.

A filter counts as active when it has at least one gender AND at least one size
category (clothing / pants / shoes / one-size). The HTMX form no longer has an
"Enabled" checkbox; the matcher infers activity from the data shape, and
"forever snooze" is the path to temporarily disable a fully-configured filter.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from uniqlo_sales_alerter.api.schemas import SavedFilterCreate, SavedFilterUpdate
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.services.saved_filters import (
    create_filter,
    list_filters,
    update_filter,
)


def _clean() -> None:
    async def _do():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))

    asyncio.run(_do())


def _create(**fields) -> int:
    _clean()

    async def _do():
        async with async_session_factory() as session:
            async with session.begin():
                payload = SavedFilterCreate(**fields)
                row = await create_filter(session, payload)
                return row.id

    return asyncio.run(_do())


def _fetch_enabled(filter_id: int) -> bool:
    async def _do():
        async with async_session_factory() as session:
            rows = await list_filters(session)
            for row in rows:
                if row.id == filter_id:
                    return row.enabled
            raise AssertionError(f"filter {filter_id} not found")

    return asyncio.run(_do())


def test_enabled_true_when_gender_and_sizes_present() -> None:
    filter_id = _create(name="A", gender=["men"], sizes_clothing=["M"])
    assert _fetch_enabled(filter_id) is True


def test_enabled_false_when_no_gender() -> None:
    filter_id = _create(name="B", gender=[], sizes_clothing=["M"])
    assert _fetch_enabled(filter_id) is False


def test_enabled_false_when_no_sizes() -> None:
    filter_id = _create(name="C", gender=["men"])
    assert _fetch_enabled(filter_id) is False


def test_enabled_true_when_one_size_match_set() -> None:
    """One-size accessories/bags counts as a valid size category."""
    filter_id = _create(name="D", gender=["unisex"], one_size_match=True)
    assert _fetch_enabled(filter_id) is True


def test_enabled_derived_on_update_too() -> None:
    """Stripping all sizes via an update flips enabled back to False."""
    filter_id = _create(name="E", gender=["men"], sizes_clothing=["M"])
    assert _fetch_enabled(filter_id) is True

    async def _strip():
        async with async_session_factory() as session:
            async with session.begin():
                payload = SavedFilterUpdate(name="E", gender=["men"])
                await update_filter(session, filter_id, payload)

    asyncio.run(_strip())
    assert _fetch_enabled(filter_id) is False


def test_explicit_enabled_true_is_ignored_without_data() -> None:
    """Even ``enabled=True`` in the payload yields a disabled filter without sizes.

    Rationale: the matcher should not waste cycles on filters that match nothing.
    Users wanting to temporarily disable a configured filter should snooze it.
    """
    filter_id = _create(name="F", gender=["men"], enabled=True)
    assert _fetch_enabled(filter_id) is False

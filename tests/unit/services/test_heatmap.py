"""Heatmap aggregation: cell counts, opacity, insufficient-data state, deep filter."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import DealObservation
from uniqlo_sales_alerter.services.heatmap import (
    INSUFFICIENT_DATA_DAYS,
    aggregate,
)


@pytest.fixture(autouse=True)
def _clean_observations():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM deal_observations"))

    asyncio.run(_truncate())
    yield


async def _insert(
    *, days_ago: int, hour_utc: int, deep: bool = True, product_id: str = "E001"
) -> None:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(
        hour=hour_utc, minute=15, second=0, microsecond=0,
        tzinfo=None,
    )
    async with async_session_factory() as session:
        async with session.begin():
            session.add(
                DealObservation(
                    observed_at=when,
                    product_id=product_id,
                    discount_pct=60.0,
                    is_deep=int(deep),
                )
            )


@pytest.mark.asyncio
async def test_empty_table_returns_all_zero_cells_and_insufficient() -> None:
    view = await aggregate()
    assert len(view.cells) == 7 * 24
    assert view.max_count == 0
    assert view.distinct_days == 0
    assert view.sufficient is False
    for cell in view.cells:
        assert cell.count == 0
        assert cell.opacity == 0.05


@pytest.mark.asyncio
async def test_single_observation_lands_in_correct_cell() -> None:
    # Pick a known time: 5 days ago at 14:00 UTC
    await _insert(days_ago=5, hour_utc=14, deep=True)
    view = await aggregate()
    assert view.max_count == 1
    matching = [c for c in view.cells if c.hour_of_day == 14 and c.count == 1]
    assert len(matching) == 1
    assert matching[0].opacity == 1.0


@pytest.mark.asyncio
async def test_opacity_scales_to_max_count() -> None:
    # 3 hits at hour 14, 1 hit at hour 9 — relative opacity should be 1.0 and ~0.33
    for _ in range(3):
        await _insert(days_ago=2, hour_utc=14, deep=True)
    await _insert(days_ago=2, hour_utc=9, deep=True)

    view = await aggregate()
    hi = next(c for c in view.cells if c.count == 3)
    lo = next(c for c in view.cells if c.count == 1)
    assert hi.opacity == 1.0
    assert abs(lo.opacity - 1 / 3) < 0.01


@pytest.mark.asyncio
async def test_only_deep_flag_filters_non_deep_rows() -> None:
    await _insert(days_ago=2, hour_utc=14, deep=True)
    await _insert(days_ago=2, hour_utc=14, deep=False, product_id="E002")
    view_deep = await aggregate(only_deep=True)
    view_all = await aggregate(only_deep=False)
    deep_cell = next(c for c in view_deep.cells if c.count > 0)
    all_cell = next(c for c in view_all.cells if c.count > 0)
    assert deep_cell.count == 1
    assert all_cell.count == 2


@pytest.mark.asyncio
async def test_lookback_window_excludes_older_observations() -> None:
    await _insert(days_ago=100, hour_utc=10, deep=True)  # outside 90-day window
    await _insert(days_ago=10, hour_utc=10, deep=True)
    view = await aggregate(lookback_days=90)
    assert view.max_count == 1
    # Distinct days counts ALL rows (not filtered by lookback) per implementation
    # so both observations contribute to the threshold check.
    assert view.distinct_days >= 1


@pytest.mark.asyncio
async def test_sufficient_threshold_at_14_distinct_days() -> None:
    for d in range(INSUFFICIENT_DATA_DAYS):
        await _insert(days_ago=d, hour_utc=12, deep=True)
    view = await aggregate()
    assert view.distinct_days == INSUFFICIENT_DATA_DAYS
    assert view.sufficient is True


@pytest.mark.asyncio
async def test_insufficient_below_14_distinct_days() -> None:
    for d in range(INSUFFICIENT_DATA_DAYS - 1):
        await _insert(days_ago=d, hour_utc=12, deep=True)
    view = await aggregate()
    assert view.sufficient is False


@pytest.mark.asyncio
async def test_cells_returned_in_predictable_dow_then_hod_order() -> None:
    view = await aggregate()
    assert view.cells[0].day_of_week == 0 and view.cells[0].hour_of_day == 0
    assert view.cells[23].day_of_week == 0 and view.cells[23].hour_of_day == 23
    assert view.cells[24].day_of_week == 1 and view.cells[24].hour_of_day == 0
    assert view.cells[-1].day_of_week == 6 and view.cells[-1].hour_of_day == 23

"""run_sale_check writes one check_history row per invocation (success + failure)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import CheckHistory
from uniqlo_sales_alerter.main import AppState, run_sale_check
from uniqlo_sales_alerter.models.products import SaleCheckResult


@pytest.fixture(autouse=True)
def _clean_check_history():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM check_history"))

    asyncio.run(_truncate())
    yield


def _app_state(*, deep_threshold: int = 50) -> AppState:
    config = AppConfig.model_validate({
        "uniqlo": {"country": "nl/nl"},
        "deep_discount_threshold": deep_threshold,
    })
    state = AppState(
        config=config,
        sale_checker=MagicMock(),
        dispatcher=MagicMock(),
        scheduler=MagicMock(running=True),
    )
    return state


def _result(matching: int = 0, new: int = 0, scanned: int = 0) -> SaleCheckResult:
    from tests.conftest import sample_deal

    deals = [sample_deal(product_id=f"E{i:03d}") for i in range(matching)]
    new_deals = deals[:new]
    return SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=scanned,
        total_on_sale=scanned,
        matching_deals=deals,
        new_deals=new_deals,
    )


@pytest.mark.asyncio
async def test_writes_one_row_on_successful_check():
    state = _app_state()
    state.sale_checker.check = AsyncMock(return_value=_result(matching=3, new=2, scanned=100))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(select(CheckHistory))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.deals_scanned == 100
    assert row.deals_matched == 3
    assert row.error is None
    assert row.duration_ms >= 0


@pytest.mark.asyncio
async def test_writes_error_row_on_failure():
    state = _app_state()
    state.sale_checker.check = AsyncMock(side_effect=RuntimeError("uniqlo offline"))

    with pytest.raises(RuntimeError):
        await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(select(CheckHistory))).scalars().all()
    assert len(rows) == 1
    assert "uniqlo offline" in rows[0].error
    assert rows[0].deals_scanned == 0


@pytest.mark.asyncio
async def test_deep_discount_count_uses_configured_threshold():
    """Items with discount >= threshold AND has_known_discount=True count as deep."""
    from tests.conftest import sample_deal

    state = _app_state(deep_threshold=50)
    deals = [
        sample_deal(product_id="E001", discount_percentage=30.0, has_known_discount=True),
        sample_deal(product_id="E002", discount_percentage=60.0, has_known_discount=True),
        sample_deal(product_id="E003", discount_percentage=80.0, has_known_discount=True),
        sample_deal(product_id="E004", discount_percentage=90.0, has_known_discount=False),
    ]
    result = SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=10,
        total_on_sale=10,
        matching_deals=deals,
        new_deals=[],
    )
    state.sale_checker.check = AsyncMock(return_value=result)
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        row = (await session.execute(select(CheckHistory))).scalar_one()
    assert row.deep_discounts == 2  # 60% and 80%; 30% is below; 90% is unknown discount


@pytest.mark.asyncio
async def test_does_not_dispatch_when_no_new_deals_for_new_deals_mode():
    state = _app_state()
    state.config.notifications.notify_on = "new_deals"
    state.sale_checker.check = AsyncMock(return_value=_result(matching=3, new=0, scanned=10))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)
    state.dispatcher.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_dispatches_all_matching_for_every_check_mode():
    state = _app_state()
    state.config.notifications.notify_on = "every_check"
    state.sale_checker.check = AsyncMock(return_value=_result(matching=3, new=0, scanned=10))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)
    state.dispatcher.dispatch.assert_awaited_once()
    args = state.dispatcher.dispatch.call_args[0][0]
    assert len(args) == 3

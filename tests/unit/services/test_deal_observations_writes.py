"""run_sale_check inserts one deal_observations row per matched deal."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from tests.conftest import sample_deal
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import DealObservation
from uniqlo_sales_alerter.main import AppState, run_sale_check
from uniqlo_sales_alerter.models.products import SaleCheckResult


@pytest.fixture(autouse=True)
def _clean_observations():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM deal_observations"))
            await conn.execute(text("DELETE FROM check_history"))

    asyncio.run(_truncate())
    yield


def _app_state(*, deep_threshold: int = 50) -> AppState:
    config = AppConfig.model_validate({
        "uniqlo": {"country": "nl/nl"},
        "deep_discount_threshold": deep_threshold,
    })
    return AppState(
        config=config,
        sale_checker=MagicMock(),
        dispatcher=MagicMock(),
        scheduler=MagicMock(running=True),
    )


@pytest.mark.asyncio
async def test_writes_one_row_per_matched_deal() -> None:
    state = _app_state(deep_threshold=50)
    deals = [
        sample_deal(product_id="E001", discount_percentage=60.0, has_known_discount=True),
        sample_deal(product_id="E002", discount_percentage=30.0, has_known_discount=True),
        sample_deal(product_id="E003", discount_percentage=0.0, has_known_discount=False),
    ]
    state.sale_checker.check = AsyncMock(return_value=SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=10,
        total_on_sale=10,
        matching_deals=deals,
        new_deals=[],
    ))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(select(DealObservation))).scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_is_deep_flag_uses_configured_threshold() -> None:
    state = _app_state(deep_threshold=50)
    deals = [
        sample_deal(product_id="E001", discount_percentage=80.0, has_known_discount=True),
        sample_deal(product_id="E002", discount_percentage=40.0, has_known_discount=True),
    ]
    state.sale_checker.check = AsyncMock(return_value=SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=5,
        total_on_sale=5,
        matching_deals=deals,
        new_deals=[],
    ))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(DealObservation).order_by(DealObservation.product_id)
        )).scalars().all()
    assert rows[0].product_id == "E001"
    assert rows[0].is_deep == 1
    assert rows[1].product_id == "E002"
    assert rows[1].is_deep == 0


@pytest.mark.asyncio
async def test_unknown_discount_is_never_deep() -> None:
    """Items without a known discount can't qualify as deep no matter what."""
    state = _app_state(deep_threshold=50)
    deals = [
        sample_deal(
            product_id="E001",
            discount_percentage=80.0,
            has_known_discount=False,
        ),
    ]
    state.sale_checker.check = AsyncMock(return_value=SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=1,
        total_on_sale=1,
        matching_deals=deals,
        new_deals=[],
    ))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        row = (await session.execute(select(DealObservation))).scalar_one()
    assert row.is_deep == 0
    assert row.discount_pct is None


@pytest.mark.asyncio
async def test_no_writes_on_empty_match_set() -> None:
    state = _app_state()
    state.sale_checker.check = AsyncMock(return_value=SaleCheckResult(
        checked_at=datetime.now(timezone.utc),
        total_products_scanned=0,
        total_on_sale=0,
        matching_deals=[],
        new_deals=[],
    ))
    state.dispatcher.dispatch = AsyncMock()

    await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(select(DealObservation))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_failed_check_does_not_write_observations() -> None:
    """If sale_checker.check raises, no observations should land."""
    state = _app_state()
    state.sale_checker.check = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await run_sale_check(state)

    async with async_session_factory() as session:
        rows = (await session.execute(select(DealObservation))).scalars().all()
    assert rows == []

"""End-to-end: a saved filter → SaleChecker → matched_filter_ids on the result.

Uses a fake :class:`SaleSourceClient` so no HTTP is involved. Verifies the
PR-4 contract: deals matching a saved filter come back tagged with that
filter's ID, and a follow-up check sees an empty ``new_deals`` (the durable
seen_variants table dedups across calls).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_raw_product
from tests.unit.clients.test_protocol_conformance import _FakeSaleSourceClient
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.models.products import UniqloProduct
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


async def _insert(**fields) -> int:
    defaults = dict(
        name="default",
        gender=["men"],
        min_discount=40.0,
        sizes_clothing=["M"],
        sizes_pants=[],
        sizes_shoes=[],
        one_size_match=0,
        availability_mode="both",
        ignored_keywords=[],
        enabled=1,
    )
    defaults.update(fields)
    row = SavedFilter(**defaults)
    async with async_session_factory() as session:
        async with session.begin():
            session.add(row)
        await session.refresh(row)
        return row.id


def _make_men_product() -> UniqloProduct:
    return UniqloProduct.model_validate(
        make_raw_product(
            product_id="E001",
            gender="MEN",
            base_price=100,
            promo_price=40,  # 60% off
            sizes=["M"],
        )
    )


@pytest.mark.asyncio
async def test_matched_filter_ids_attached_on_check() -> None:
    filter_id = await _insert(name="NL men 40+ M")
    product = _make_men_product()
    fake_client = _FakeSaleSourceClient([product])

    config = AppConfig.model_validate({"uniqlo": {"country": "nl/nl"}})
    checker = SaleChecker(config, client=fake_client)
    with patch.object(
        checker._stock_verifier, "verify", new=AsyncMock(side_effect=lambda items: items)
    ):
        result = await checker.check()

    assert len(result.matching_deals) == 1
    assert result.matching_deals[0].matched_filter_ids == [filter_id]
    assert len(result.new_deals) == 1


@pytest.mark.asyncio
async def test_second_check_finds_no_new_deals() -> None:
    await _insert(name="NL men 40+ M")
    product = _make_men_product()
    fake_client = _FakeSaleSourceClient([product])

    config = AppConfig.model_validate({
        "uniqlo": {"country": "nl/nl"},
        "notifications": {"notify_on": "new_deals"},
    })
    checker = SaleChecker(config, client=fake_client)
    with patch.object(
        checker._stock_verifier, "verify", new=AsyncMock(side_effect=lambda items: items)
    ):
        first = await checker.check()
        second = await checker.check()

    assert len(first.new_deals) == 1
    assert second.new_deals == []

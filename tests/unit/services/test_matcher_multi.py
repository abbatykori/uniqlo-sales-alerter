"""Multi-filter tagging — a deal that matches A and B but not C tags both IDs."""

from __future__ import annotations

import pytest

from tests.conftest import make_raw_product
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.models.products import UniqloProduct
from uniqlo_sales_alerter.services.matcher import Matcher


def _product(**kw) -> UniqloProduct:
    return UniqloProduct.model_validate(make_raw_product(**kw))


async def _insert(**fields) -> int:
    defaults = dict(
        name="default",
        gender=[],
        min_discount=0.0,
        sizes_clothing=[],
        sizes_pants=[],
        sizes_shoes=[],
        one_size_match=0,
        availability_mode="both",
        ignored_keywords=[],
        enabled=1,
        snooze_until=None,
    )
    defaults.update(fields)
    row = SavedFilter(**defaults)
    async with async_session_factory() as session:
        async with session.begin():
            session.add(row)
        await session.refresh(row)
        return row.id


def _matcher() -> Matcher:
    return Matcher(
        AppConfig.model_validate({"uniqlo": {"country": "nl/nl"}}),
        async_session_factory,
    )


_NO_WATCH = dict(
    watched_ids=set(),
    watched_by_product={},
    ignored_ids=set(),
    global_ignored_keywords=[],
)


@pytest.mark.asyncio
async def test_product_matches_two_of_three_filters() -> None:
    """A MEN/size-M/60%-off deal matches A (men/M/40+) and B (any/M/50+), not C (women)."""
    id_a = await _insert(name="A men M 40+", gender=["men"], sizes_clothing=["M"], min_discount=40)
    id_b = await _insert(name="B any M 50+", gender=[], sizes_clothing=["M"], min_discount=50)
    await _insert(name="C women M 40+", gender=["women"], sizes_clothing=["M"], min_discount=40)

    matcher = _matcher()
    products = [_product(product_id="E001", gender="MEN", base_price=100, promo_price=40,
                         sizes=["M"])]
    result = await matcher.apply(products, **_NO_WATCH)

    assert len(result) == 1
    assert sorted(result[0].matched_filter_ids) == sorted([id_a, id_b])


@pytest.mark.asyncio
async def test_one_product_per_emitted_row_even_with_multi_match() -> None:
    """Three filters all matching the same product → still one SaleItem in the result."""
    await _insert(name="F1", min_discount=0)
    await _insert(name="F2", min_discount=0)
    await _insert(name="F3", min_discount=0)
    matcher = _matcher()
    products = [_product(product_id="E001", promo_price=40)]
    result = await matcher.apply(products, **_NO_WATCH)
    assert len(result) == 1
    assert len(result[0].matched_filter_ids) == 3


@pytest.mark.asyncio
async def test_product_matching_no_filter_is_not_emitted() -> None:
    await _insert(name="men only", gender=["men"], min_discount=0)
    matcher = _matcher()
    products = [_product(product_id="E001", gender="WOMEN", promo_price=40)]
    result = await matcher.apply(products, **_NO_WATCH)
    assert result == []


@pytest.mark.asyncio
async def test_watched_product_emits_with_empty_matched_filter_ids() -> None:
    """Watched-variant bypass: emit the deal even with zero filter matches; tag list is []."""
    await _insert(name="strict-men", gender=["men"], sizes_clothing=["M"], min_discount=80)
    matcher = _matcher()
    products = [_product(product_id="E001", gender="WOMEN", base_price=100, promo_price=90)]
    result = await matcher.apply(
        products,
        watched_ids={"E001"},
        watched_by_product={"E001": []},
        ignored_ids=set(),
        global_ignored_keywords=[],
    )
    assert len(result) == 1
    assert result[0].is_watched is True
    assert result[0].matched_filter_ids == []

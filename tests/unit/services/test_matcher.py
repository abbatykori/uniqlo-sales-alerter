"""Matcher × gender / discount / sizes / ignored_keywords / snooze matrix."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_raw_product
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.models.products import UniqloProduct
from uniqlo_sales_alerter.services.matcher import Matcher


def _product(**kw) -> UniqloProduct:
    return UniqloProduct.model_validate(make_raw_product(**kw))


async def _insert_filter(**fields) -> int:
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


def _matcher(country: str = "nl/nl") -> Matcher:
    cfg = AppConfig.model_validate({"uniqlo": {"country": country}})
    return Matcher(cfg, async_session_factory)


# Common matcher.apply kwargs (no watched/ignored set up).
_NO_WATCH = dict(
    watched_ids=set(),
    watched_by_product={},
    ignored_ids=set(),
    global_ignored_keywords=[],
)


@pytest.mark.asyncio
async def test_no_active_filters_returns_only_watched() -> None:
    matcher = _matcher()
    products = [_product(product_id="E001", promo_price=40)]  # default discount
    result = await matcher.apply(products, **_NO_WATCH)
    assert result == []


@pytest.mark.asyncio
async def test_gender_filter_rejects_other_genders() -> None:
    await _insert_filter(name="men only", gender=["men"], min_discount=0)
    matcher = _matcher()
    products = [
        _product(product_id="E001", gender="MEN", promo_price=40),
        _product(product_id="E002", gender="WOMEN", promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E001"}


@pytest.mark.asyncio
async def test_unisex_always_passes_gender() -> None:
    await _insert_filter(name="men only", gender=["men"], min_discount=0)
    matcher = _matcher()
    products = [_product(product_id="E001", gender="UNISEX", promo_price=40)]
    result = await matcher.apply(products, **_NO_WATCH)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_min_discount_filters_below_threshold() -> None:
    await _insert_filter(name="40+", gender=[], min_discount=40)
    matcher = _matcher()
    products = [
        _product(product_id="E001", base_price=100, promo_price=70),  # 30% off
        _product(product_id="E002", base_price=100, promo_price=40),  # 60% off
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E002"}


@pytest.mark.asyncio
async def test_size_filter_clothing() -> None:
    await _insert_filter(name="M only", sizes_clothing=["M"], min_discount=0)
    matcher = _matcher()
    products = [
        _product(product_id="E001", sizes=["M"]),
        _product(product_id="E002", sizes=["L"]),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E001"}


@pytest.mark.asyncio
async def test_one_size_match_enables_one_size_products() -> None:
    await _insert_filter(name="ones", one_size_match=1, min_discount=0)
    matcher = _matcher()
    products = [
        _product(product_id="E001", sizes=["One Size"]),
        _product(product_id="E002", sizes=["S", "M"]),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E001"}


@pytest.mark.asyncio
async def test_per_filter_ignored_keywords_drop_match() -> None:
    await _insert_filter(
        name="no-jacket",
        gender=[],
        ignored_keywords=["jacket"],
        min_discount=0,
    )
    matcher = _matcher()
    products = [
        _product(product_id="E001", name="Soft Jacket", promo_price=40),
        _product(product_id="E002", name="Cotton T-Shirt", promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E002"}


@pytest.mark.asyncio
async def test_global_ignored_keywords_drop_match_across_filters() -> None:
    await _insert_filter(name="anything", min_discount=0)
    matcher = _matcher()
    products = [
        _product(product_id="E001", name="Beige Coat", promo_price=40),
        _product(product_id="E002", name="Heavy Jacket", promo_price=40),
    ]
    result = await matcher.apply(
        products,
        watched_ids=set(),
        watched_by_product={},
        ignored_ids=set(),
        global_ignored_keywords=["jacket"],
    )
    assert {r.product_id for r in result} == {"E001"}


@pytest.mark.asyncio
async def test_ignored_product_id_drops_via_prefix_match() -> None:
    await _insert_filter(name="any", min_discount=0)
    matcher = _matcher()
    products = [
        _product(product_id="E001-000", promo_price=40),
        _product(product_id="E002-000", promo_price=40),
    ]
    result = await matcher.apply(
        products,
        watched_ids=set(),
        watched_by_product={},
        ignored_ids={"E001"},
        global_ignored_keywords=[],
    )
    assert {r.product_id for r in result} == {"E002-000"}


@pytest.mark.asyncio
async def test_disabled_filter_is_not_loaded() -> None:
    await _insert_filter(name="off", enabled=0, min_discount=0)
    matcher = _matcher()
    products = [_product(product_id="E001", promo_price=40)]
    result = await matcher.apply(products, **_NO_WATCH)
    assert result == []


@pytest.mark.asyncio
async def test_snoozed_filter_excluded_until_expiry() -> None:
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=1)
    past = now - timedelta(days=1)
    await _insert_filter(name="future-snooze", snooze_until=future, min_discount=0)
    await _insert_filter(name="past-snooze", snooze_until=past, min_discount=0)
    matcher = _matcher()
    products = [_product(product_id="E001", promo_price=40)]
    result = await matcher.apply(products, **_NO_WATCH)
    # The expired snooze is now active; one row in matched_filter_ids.
    assert len(result) == 1
    assert len(result[0].matched_filter_ids) == 1

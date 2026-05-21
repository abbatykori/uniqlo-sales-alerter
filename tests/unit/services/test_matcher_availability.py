"""availability_mode logic — online/in_store/both + unreliable-country fallback."""

from __future__ import annotations

import pytest

from tests.conftest import make_raw_product
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.models.products import UniqloProduct
from uniqlo_sales_alerter.services.matcher import Matcher


def _product(*, store_only: bool, **kw) -> UniqloProduct:
    raw = make_raw_product(**kw)
    raw["storeStockOnly"] = store_only
    return UniqloProduct.model_validate(raw)


async def _insert(mode: str) -> int:
    row = SavedFilter(
        name=f"mode-{mode}",
        gender=[],
        min_discount=0.0,
        sizes_clothing=[],
        sizes_pants=[],
        sizes_shoes=[],
        one_size_match=0,
        availability_mode=mode,
        ignored_keywords=[],
        enabled=1,
    )
    async with async_session_factory() as session:
        async with session.begin():
            session.add(row)
        await session.refresh(row)
        return row.id


def _matcher(country: str = "nl/nl") -> Matcher:
    cfg = AppConfig.model_validate({"uniqlo": {"country": country}})
    return Matcher(cfg, async_session_factory)


_NO_WATCH = dict(
    watched_ids=set(),
    watched_by_product={},
    ignored_ids=set(),
    global_ignored_keywords=[],
)


@pytest.mark.asyncio
async def test_both_includes_everything() -> None:
    await _insert("both")
    matcher = _matcher()
    products = [
        _product(product_id="E_ONLINE", store_only=False, promo_price=40),
        _product(product_id="E_STORE", store_only=True, promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E_ONLINE", "E_STORE"}


@pytest.mark.asyncio
async def test_online_excludes_store_only() -> None:
    await _insert("online")
    matcher = _matcher()
    products = [
        _product(product_id="E_ONLINE", store_only=False, promo_price=40),
        _product(product_id="E_STORE", store_only=True, promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E_ONLINE"}


@pytest.mark.asyncio
async def test_in_store_excludes_online_only() -> None:
    await _insert("in_store")
    matcher = _matcher()
    products = [
        _product(product_id="E_ONLINE", store_only=False, promo_price=40),
        _product(product_id="E_STORE", store_only=True, promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E_STORE"}


@pytest.mark.parametrize("country", ["ph/en", "th/en", "kr/ko"])
@pytest.mark.asyncio
async def test_in_store_falls_back_to_both_for_unreliable_countries(
    country: str, caplog,
) -> None:
    """Unreliable countries: in_store filter degrades to 'both' with a warning."""
    import logging

    await _insert("in_store")
    matcher = _matcher(country)
    products = [
        _product(product_id="E_ONLINE", store_only=False, promo_price=40),
        _product(product_id="E_STORE", store_only=True, promo_price=40),
    ]
    with caplog.at_level(logging.WARNING):
        result = await matcher.apply(products, **_NO_WATCH)
    assert {r.product_id for r in result} == {"E_ONLINE", "E_STORE"}
    assert any("storeStockOnly flag unreliable" in r.message for r in caplog.records)


@pytest.mark.parametrize("country", ["ph/en", "th/en"])
@pytest.mark.asyncio
async def test_online_mode_on_unreliable_countries_acts_as_both(country: str) -> None:
    """Online mode on unreliable countries is also permissive — we don't trust the flag."""
    await _insert("online")
    matcher = _matcher(country)
    products = [
        _product(product_id="E_STORE", store_only=True, promo_price=40),
    ]
    result = await matcher.apply(products, **_NO_WATCH)
    assert len(result) == 1

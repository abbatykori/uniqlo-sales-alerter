"""Step-8 model additions: store_stock_only on UniqloProduct, matched_filter_ids on SaleItem."""

from __future__ import annotations

from tests.conftest import make_raw_product, sample_deal
from uniqlo_sales_alerter.models.products import UniqloProduct


def test_uniqlo_product_parses_store_stock_only_from_raw() -> None:
    raw = make_raw_product()
    raw["storeStockOnly"] = True
    product = UniqloProduct.model_validate(raw)
    assert product.store_stock_only is True


def test_uniqlo_product_store_stock_only_defaults_to_false() -> None:
    raw = make_raw_product()
    raw.pop("storeStockOnly", None)
    product = UniqloProduct.model_validate(raw)
    assert product.store_stock_only is False


def test_sale_item_matched_filter_ids_defaults_empty() -> None:
    item = sample_deal()
    assert item.matched_filter_ids == []


def test_sale_item_matched_filter_ids_round_trips() -> None:
    item = sample_deal(matched_filter_ids=[1, 7])
    assert item.matched_filter_ids == [1, 7]
    dumped = item.model_dump()
    assert dumped["matched_filter_ids"] == [1, 7]

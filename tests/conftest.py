"""Shared fixtures and realistic Uniqlo API mock data."""

from __future__ import annotations

import os
import pathlib
import tempfile

# Pin the test database path before any uniqlo_sales_alerter import. The
# db.engine module captures DATABASE_URL at import time, so this env var
# must be set first.
_TEST_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "uniqlo-alerter-pytest.db"
os.environ.setdefault("ALERTER_DB_PATH", str(_TEST_DB_PATH))

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

from uniqlo_sales_alerter.config import AppConfig  # noqa: E402
from uniqlo_sales_alerter.db.schema import upgrade_to_head  # noqa: E402
from uniqlo_sales_alerter.models.products import SaleItem  # noqa: E402
from uniqlo_sales_alerter.services.sale_checker import SaleChecker  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_db() -> object:
    """Apply Alembic migrations once per test session against a fresh SQLite file."""
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
    upgrade_to_head()
    yield
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()

_SAMPLE_BASE_URL = "https://www.uniqlo.com/de/de/products/E123456-000/00?colorDisplayCode=00"


def sample_deal(**overrides) -> SaleItem:
    """Build a realistic SaleItem for tests — shared across test modules."""
    defaults = dict(
        product_id="E123456-000",
        name="Test T-Shirt",
        original_price=39.90,
        sale_price=19.90,
        currency_symbol="€",
        discount_percentage=50.1,
        gender="MEN",
        available_sizes=["S", "M", "L"],
        image_url="https://image.uniqlo.com/test.jpg",
        product_urls=[
            f"{_SAMPLE_BASE_URL}&sizeDisplayCode=001",
            f"{_SAMPLE_BASE_URL}&sizeDisplayCode=002",
            f"{_SAMPLE_BASE_URL}&sizeDisplayCode=003",
        ],
        color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"],
        is_watched=False,
    )
    defaults.update(overrides)
    return SaleItem(**defaults)


def noop_verify(checker: SaleChecker):
    """Patch ``_verify_stock`` to be a passthrough (tests focus on filter logic)."""
    return patch.object(
        checker, "_verify_stock",
        new_callable=AsyncMock,
        side_effect=lambda items: items,
    )


def noop_watched_fetch(checker: SaleChecker):
    """Patch ``fetch_products_by_ids`` to return nothing (no extra watched fetches)."""
    return patch.object(
        checker._client, "fetch_products_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    )


def make_raw_product(
    *,
    product_id: str = "E100000-000",
    name: str = "Test Product",
    gender: str = "MEN",
    base_price: float = 39.90,
    promo_price: float | None = None,
    sizes: list[str] | None = None,
    image_url: str | None = "https://image.uniqlo.com/test.jpg",
) -> dict:
    """Build a raw product dict matching the Uniqlo API response shape."""
    sizes = sizes or ["S", "M", "L"]
    size_list = [
        {
            "code": f"SMA{i:03d}",
            "displayCode": f"{i:03d}",
            "name": s,
            "display": {"showFlag": True, "chipType": 0},
        }
        for i, s in enumerate(sizes, start=1)
    ]
    prices: dict = {
        "base": {"currency": {"code": "EUR", "symbol": "€"}, "value": base_price},
        "promo": (
            {"currency": {"code": "EUR", "symbol": "€"}, "value": promo_price}
            if promo_price is not None
            else None
        ),
        "isDualPrice": promo_price is not None,
    }
    images = {}
    if image_url:
        images = {"main": {"00": {"image": image_url, "model": []}}, "chip": {}, "sub": []}

    return {
        "productId": product_id,
        "name": name,
        "genderCategory": gender,
        "genderName": gender.title(),
        "prices": prices,
        "sizes": size_list,
        "images": images,
        "priceGroup": "00",
        "rating": {"average": 4.5, "count": 42},
        "representative": {"sales": promo_price is not None},
        "plds": [],
        "colors": [],
        "representativeColorDisplayCode": "00",
        "sizeGender": gender,
        "storeStockOnly": False,
    }


def make_api_response(products: list[dict], total: int | None = None) -> dict:
    """Wrap product dicts in the Uniqlo API envelope."""
    if total is None:
        total = len(products)
    return {
        "status": "ok",
        "result": {
            "items": products,
            "pagination": {"total": total, "offset": 0, "count": len(products)},
            "aggregations": {},
        },
    }


@pytest.fixture()
def default_config() -> AppConfig:
    return AppConfig()


@pytest.fixture()
def sale_config() -> AppConfig:
    """Config tuned for testing sale filtering."""
    return AppConfig.model_validate(
        {
            "uniqlo": {"country": "de/de", "check_interval_minutes": 60},
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"clothing": ["M", "L"], "pants": ["32inch"]},
                "watched_variants": [
                    {"id": "E999999-001", "color": "09", "size": "002"},
                ],
            },
            "notifications": {},
        }
    )

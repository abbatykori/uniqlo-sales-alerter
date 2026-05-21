"""SaleSourceClient Protocol conformance.

Ensures the real :class:`UniqloClient` satisfies the protocol at runtime and
that a fake implementation (used in step-8 tests) also conforms. ``@runtime_checkable``
on the Protocol allows ``isinstance`` checks; the fake's existence proves the
protocol is small enough to mock without subclassing.
"""

from __future__ import annotations

from uniqlo_sales_alerter.clients import SaleSourceClient, UniqloClient
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.models.products import UniqloProduct


class _FakeSaleSourceClient:
    """Trivial in-memory client used by step-8 matcher/state tests."""

    def __init__(self, products: list[UniqloProduct] | None = None) -> None:
        self._products = list(products or [])
        self.closed = False

    async def fetch_sale_products(self) -> list[UniqloProduct]:
        return list(self._products)

    async def fetch_all_products(self) -> list[UniqloProduct]:
        return list(self._products)

    async def fetch_products_by_ids(
        self, product_ids: list[str]
    ) -> list[UniqloProduct]:
        wanted = set(product_ids)
        return [p for p in self._products if p.product_id in wanted]

    async def fetch_product_l2s(
        self, product_id: str, price_group: str
    ) -> list[dict]:
        return []

    async def fetch_variant_stock(
        self, product_id: str, price_group: str
    ) -> dict[str, dict]:
        return {}

    async def aclose(self) -> None:
        self.closed = True


def test_uniqlo_client_satisfies_protocol() -> None:
    client = UniqloClient(AppConfig())
    assert isinstance(client, SaleSourceClient)


def test_fake_client_satisfies_protocol() -> None:
    assert isinstance(_FakeSaleSourceClient(), SaleSourceClient)

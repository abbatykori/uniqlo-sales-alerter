"""Sale-source client protocol.

Defines the abstract interface the matcher, stock verifier, and enrichment
service depend on. The concrete implementation today is
:class:`uniqlo_sales_alerter.clients.uniqlo.UniqloClient`. Tests can supply
any duck-typed implementation (e.g. a stubbed fake) that conforms to this
protocol without having to subclass ``UniqloClient``.

``@runtime_checkable`` lets us assert conformance via ``isinstance`` in
tests, mirroring the protocol-based pattern already in use for
:mod:`uniqlo_sales_alerter.notifications.base`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from uniqlo_sales_alerter.models.products import UniqloProduct


@runtime_checkable
class SaleSourceClient(Protocol):
    """Async HTTP-like interface to a product catalogue with stock data."""

    async def fetch_sale_products(self) -> list[UniqloProduct]:
        """Return all currently sale-flagged products."""

    async def fetch_all_products(self) -> list[UniqloProduct]:
        """Return the full catalogue (sale or not), handling pagination."""

    async def fetch_products_by_ids(
        self, product_ids: list[str]
    ) -> list[UniqloProduct]:
        """Return products matching specific IDs, regardless of sale status."""

    async def fetch_product_l2s(
        self, product_id: str, price_group: str
    ) -> list[dict]:
        """Return the L2 variant rows (colour x size) for a single product."""

    async def fetch_variant_stock(
        self, product_id: str, price_group: str
    ) -> dict[str, dict]:
        """Return per-variant stock info keyed by ``l2Id``."""

    async def aclose(self) -> None:
        """Close any underlying connections."""

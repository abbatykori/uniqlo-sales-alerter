"""Core service that orchestrates sale checks.

Delegates to focused modules:

- :mod:`~.filters` — product filtering pipeline
- :mod:`~.stock` — real-time stock verification
- :mod:`~.state` — seen-variant persistence for new-deal detection
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uniqlo_sales_alerter.clients import SaleSourceClient, UniqloClient
from uniqlo_sales_alerter.db.engine import async_session_factory as default_session_factory
from uniqlo_sales_alerter.models.products import SaleCheckResult, UniqloProduct
from uniqlo_sales_alerter.services.filters import apply_filters as _legacy_apply_filters
from uniqlo_sales_alerter.services.matcher import Matcher
from uniqlo_sales_alerter.services.state import SeenVariantStore
from uniqlo_sales_alerter.services.stock import StockVerifier

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import AppConfig, WatchedVariant

logger = logging.getLogger(__name__)


class SaleChecker:
    """Fetches products, filters for matching deals, and caches results."""

    def __init__(
        self,
        config: AppConfig,
        *,
        client: SaleSourceClient | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._config = config
        self._client: SaleSourceClient = client or UniqloClient(config)
        self._session_factory = session_factory or default_session_factory
        self.last_result: SaleCheckResult | None = None

        self._watched_ids, self._watched_by_product = self._index_watched(
            config.filters.watched_variants,
        )
        self._ignored_ids: set[str] = {
            p.id.upper() for p in config.filters.ignored_products
        }
        self._ignored_keywords: list[str] = [
            kw.lower() for kw in config.filters.ignored_keywords if kw.strip()
        ]

        self._state = SeenVariantStore(
            self._session_factory,
            suppress_low_stock=config.notifications.suppress_low_stock_alerts,
            low_stock_threshold=config.notifications.low_stock_threshold,
        )
        # Lazy seen-set: loaded on first check() so __init__ stays sync.
        self._seen_variants: set[str] | None = None

        self._stock_verifier = StockVerifier(
            self._client, config, self._watched_by_product,
        )

        self._matcher = Matcher(config, self._session_factory)

    @property
    def http_client(self) -> SaleSourceClient:
        """The underlying catalogue client."""
        return self._client

    async def close(self) -> None:
        """Release underlying HTTP resources."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Main check pipeline
    # ------------------------------------------------------------------

    async def check(self) -> SaleCheckResult:
        """Run a full sale check: fetch, filter, verify stock, detect new deals."""
        sale_products = await self._client.fetch_sale_products()
        logger.debug("Fetched %d sale products from Uniqlo API", len(sale_products))

        all_products = await self._include_watched_products(sale_products)
        sale_pids = {p.product_id.upper() for p in sale_products}

        matching = await self._matcher.apply(
            all_products,
            watched_ids=self._watched_ids,
            watched_by_product=self._watched_by_product,
            ignored_ids=self._ignored_ids,
            global_ignored_keywords=self._ignored_keywords,
            sale_product_ids=sale_pids,
        )
        matching = await self._verify_stock(matching)

        # Seen-set load semantics (preserved from upstream):
        # - notify_on=new_deals: load persisted set on first check; new
        #   deals are those not previously seen across restarts.
        # - notify_on=all_then_new: start with empty set each process so the
        #   first check after startup reports everything currently matched.
        # - notify_on=every_check: always empty set; every match is a new deal.
        if self._seen_variants is None:
            if self._config.notifications.notify_on == "new_deals":
                self._seen_variants = await self._state.load()
            else:
                self._seen_variants = set()

        current_variants: set[str] = set()
        for item in matching:
            current_variants |= self._variant_keys(item)

        new_deals = [
            item for item in matching
            if self._variant_keys(item) - self._seen_variants
        ]

        result = SaleCheckResult(
            total_products_scanned=len(sale_products),
            total_on_sale=len(sale_products),
            matching_deals=matching,
            new_deals=new_deals,
        )

        self._seen_variants = current_variants
        await self._state.save(current_variants)
        self.last_result = result
        return result

    # ------------------------------------------------------------------
    # Delegation methods
    # ------------------------------------------------------------------

    def _apply_filters(
        self,
        products: list[UniqloProduct],
        sale_product_ids: set[str] | None = None,
    ) -> list:
        """Sync legacy-filter delegate, kept for unit-test ergonomics.

        Production goes through ``self._matcher.apply`` in :meth:`check`. This
        helper applies the legacy ``config.filters`` single-filter pipeline
        directly — used by tests that exercise individual predicates without
        spinning up the SQLite-backed matcher loop. New behaviour (multi-filter
        matching, availability_mode, per-filter snooze) is covered by
        :mod:`tests.unit.services.test_matcher`.
        """
        return _legacy_apply_filters(
            products,
            config=self._config,
            watched_ids=self._watched_ids,
            watched_by_product=self._watched_by_product,
            ignored_ids=self._ignored_ids,
            ignored_keywords=self._ignored_keywords,
            sale_product_ids=sale_product_ids,
        )

    async def _verify_stock(self, items: list) -> list:
        """Delegate to :meth:`StockVerifier.verify`."""
        return await self._stock_verifier.verify(items)

    def _variant_keys(self, item) -> set[str]:
        """Delegate to :meth:`SeenVariantStore.variant_keys`."""
        return self._state.variant_keys(item)

    # ------------------------------------------------------------------
    # Watched product helpers
    # ------------------------------------------------------------------

    async def _include_watched_products(
        self, sale_products: list[UniqloProduct],
    ) -> list[UniqloProduct]:
        """Fetch any watched products missing from the sale results."""
        all_products: list[UniqloProduct] = list(sale_products)
        if not self._watched_ids:
            return all_products

        sale_pids = {p.product_id.upper() for p in sale_products}
        missing_upper = self._watched_ids - sale_pids
        if not missing_upper:
            return all_products

        to_fetch: set[str] = set()
        for pid_upper in missing_upper:
            for wv in self._watched_by_product.get(pid_upper, []):
                to_fetch.add(wv.id)
        watched_extra = await self._client.fetch_products_by_ids(sorted(to_fetch))
        logger.debug(
            "Fetched %d watched product(s) not currently on sale",
            len(watched_extra),
        )
        all_products.extend(watched_extra)
        return all_products

    @staticmethod
    def _index_watched(
        variants: list[WatchedVariant],
    ) -> tuple[set[str], dict[str, list[WatchedVariant]]]:
        """Index watched variants into a product-ID set and per-product map."""
        by_product: dict[str, list[WatchedVariant]] = {}
        for wv in variants:
            by_product.setdefault(wv.id.upper(), []).append(wv)
        return set(by_product.keys()), by_product

    # ------------------------------------------------------------------
    # Legacy static method kept for test compatibility
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_in_stock_variant(
        size_name: str,
        l2s: list[dict],
        stock_map: dict[str, dict],
        wanted_sizes: set[str],
        preferred_color: str | None = None,
    ) -> tuple[str, str, str, int, str, str, str] | None:
        """Thin wrapper around :func:`stock.pick_in_stock_variant`.

        Returns a plain tuple for backward compatibility with existing
        tests.  New code should use :func:`stock.pick_in_stock_variant`
        which returns a :class:`StockVariant`.
        """
        from uniqlo_sales_alerter.services.stock import pick_in_stock_variant

        sv = pick_in_stock_variant(
            size_name, l2s, stock_map, wanted_sizes,
            preferred_color=preferred_color,
        )
        if sv is None:
            return None
        return (
            sv.color_display_code, sv.size_display_code, sv.color_name,
            sv.quantity, sv.status, sv.color_code, sv.size_code,
        )

"""Multi-filter matcher reading saved filters from SQLite.

Replaces the legacy single-filter loop in :func:`services.filters.apply_filters`.
For each product the matcher iterates every enabled, non-snoozed filter and
tags the resulting :class:`SaleItem` with the IDs of filters that matched.

A deal is reported when at least one filter matches it. Watched variants
bypass all filter logic and are always emitted (with ``matched_filter_ids=[]``
serving as the sentinel for "watched, not filter-matched").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.models.products import SaleItem, UniqloProduct
from uniqlo_sales_alerter.services.filters import (
    _is_excluded,
    _is_watched,
    _matches_gender,
    _matches_size,
    _meets_discount_threshold,
    to_sale_item,
)

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import AppConfig, CountryCapabilities, WatchedVariant

logger = logging.getLogger(__name__)


def _matches_availability(
    product: UniqloProduct,
    mode: str,
    caps: CountryCapabilities,
    country_code: str,
    *,
    warned: set[str],
) -> bool:
    """Decide whether *product* satisfies the filter's ``availability_mode``.

    Returns True when the product passes. For countries whose
    ``storeStockOnly`` flag is unreliable (PH, TH, KR), an ``in_store``
    filter falls back to ``both`` with a one-shot logged warning.
    *warned* is a set of country codes already warned about in this
    matcher instance so the log doesn't spam.
    """
    if mode == "both":
        return True
    if not caps.store_stock_only_reliable:
        if mode == "in_store" and country_code not in warned:
            warned.add(country_code)
            logger.warning(
                "availability_mode=in_store falls back to 'both' for country %s "
                "(storeStockOnly flag unreliable)",
                country_code,
            )
        return True
    if mode == "online":
        return not product.store_stock_only
    if mode == "in_store":
        return product.store_stock_only
    return True


def _build_size_filter_for_saved(f: SavedFilter) -> set[str]:
    """Combine a saved filter's size lists into a single uppercase set."""
    combined: list[str] = [
        *(f.sizes_clothing or []),
        *(f.sizes_pants or []),
        *(f.sizes_shoes or []),
    ]
    result = {name.upper() for name in combined}
    if f.one_size_match:
        result.add("ONE SIZE")
    return result


def _filter_keywords_lower(f: SavedFilter) -> list[str]:
    return [kw.lower() for kw in (f.ignored_keywords or []) if kw.strip()]


class Matcher:
    """Apply enabled, non-snoozed saved filters to a product list."""

    def __init__(
        self,
        config: AppConfig,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._warned_countries: set[str] = set()
        self._last_no_filter_warning_at: datetime | None = None

    async def _load_active_filters(self, now: datetime) -> list[SavedFilter]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SavedFilter)
                .where(SavedFilter.enabled == 1)
                .where(
                    (SavedFilter.snooze_until.is_(None))
                    | (SavedFilter.snooze_until <= now)
                )
                .order_by(SavedFilter.id)
            )
            return list(result.scalars())

    def _warn_if_no_active_filters(self, now: datetime) -> None:
        last = self._last_no_filter_warning_at
        if last is None or (now - last).total_seconds() > 3600:
            logger.info(
                "No active saved filters — only watched variants will be reported"
            )
            self._last_no_filter_warning_at = now

    async def apply(
        self,
        products: list[UniqloProduct],
        *,
        watched_ids: set[str],
        watched_by_product: dict[str, list[WatchedVariant]],
        ignored_ids: set[str],
        global_ignored_keywords: list[str],
        sale_product_ids: set[str] | None = None,
        now: datetime | None = None,
    ) -> list[SaleItem]:
        now = now or datetime.now(timezone.utc)
        filters = await self._load_active_filters(now)
        if not filters:
            self._warn_if_no_active_filters(now)

        caps = self._config.capabilities
        country_code = self._config.country_code

        sale_pids = (
            sale_product_ids
            if sale_product_ids is not None
            else {p.product_id.upper() for p in products}
        )

        results: list[SaleItem] = []
        for product in products:
            watched = _is_watched(product.product_id, watched_ids)
            if not watched and _is_excluded(
                product, ignored_ids, global_ignored_keywords
            ):
                continue

            in_sale_feed = product.product_id.upper() in sale_pids
            has_known_discount = product.is_on_sale
            wv_list = watched_by_product.get(product.product_id.upper(), [])

            if watched:
                results.append(
                    to_sale_item(
                        product,
                        is_watched=True,
                        size_filter=set(),
                        watched_variants=wv_list,
                        in_sale_feed=in_sale_feed,
                        config=self._config,
                    )
                )
                continue

            matched_ids: list[int] = []
            union_size_filter: set[str] = set()
            name_lower = product.name.lower()
            for f in filters:
                gender_filter = {g.upper() for g in (f.gender or [])}
                size_filter = _build_size_filter_for_saved(f)
                filter_keywords = _filter_keywords_lower(f)

                if filter_keywords and any(
                    kw in name_lower for kw in filter_keywords
                ):
                    continue
                if not _matches_gender(product, gender_filter):
                    continue
                if not _meets_discount_threshold(
                    product, f.min_discount, has_known_discount
                ):
                    continue
                if not _matches_size(product, size_filter):
                    continue
                if not _matches_availability(
                    product,
                    f.availability_mode,
                    caps,
                    country_code,
                    warned=self._warned_countries,
                ):
                    continue

                matched_ids.append(f.id)
                union_size_filter |= size_filter

            if not matched_ids:
                continue

            item = to_sale_item(
                product,
                is_watched=False,
                size_filter=union_size_filter,
                watched_variants=wv_list,
                in_sale_feed=in_sale_feed,
                config=self._config,
            )
            item.matched_filter_ids = matched_ids
            results.append(item)

        results.sort(key=lambda i: i.discount_percentage, reverse=True)
        return results

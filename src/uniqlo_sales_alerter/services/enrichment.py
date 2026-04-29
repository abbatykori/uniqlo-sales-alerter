"""Metadata enrichment for watched variants and ignored products.

Resolves product names, human-readable colour/size names, and
reconstructs missing URLs by fetching data from the Uniqlo API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import UniqloProduct, build_product_url

if TYPE_CHECKING:
    from uniqlo_sales_alerter.clients.uniqlo import UniqloClient
    from uniqlo_sales_alerter.config import AppConfig

logger = logging.getLogger(__name__)


def _find_color_name(l2s: list[dict], color_code: str) -> str:
    """Look up the human-readable colour name from L2 variant data."""
    for l2 in l2s:
        color = l2.get("color", {})
        if color.get("displayCode") == color_code:
            return color.get("name", "")
    return ""


def _find_size_name(product: UniqloProduct, size_code: str) -> str:
    """Look up the human-readable size name from a product's size list."""
    for sz in product.sizes:
        if sz.display_code == size_code:
            return sz.name
    return ""


async def enrich_config(config: AppConfig, client: UniqloClient) -> bool:
    """Fill in missing metadata for watched variants and ignored products.

    Returns ``True`` when at least one entry was updated (caller should
    persist the config).
    """
    base = config.product_page_base

    incomplete_variants = [
        wv for wv in config.filters.watched_variants
        if wv.id and (
            not wv.name or not wv.color_name
            or not wv.size_name or not wv.url
        )
    ]
    incomplete_ignored = [
        ip for ip in config.filters.ignored_products
        if ip.id and (not ip.name or not ip.url)
    ]
    if not incomplete_variants and not incomplete_ignored:
        return False

    all_ids = list(
        {wv.id for wv in incomplete_variants}
        | {ip.id for ip in incomplete_ignored}
    )
    products = await client.fetch_products_by_ids(all_ids)
    product_by_id = {p.product_id.upper(): p for p in products}

    l2_keys = {
        (wv.id, wv.price_group)
        for wv in incomplete_variants
        if not wv.color_name or not wv.size_name
    }
    l2_by_product: dict[str, list[dict]] = {}
    for pid, pg in l2_keys:
        l2_by_product[pid.upper()] = await client.fetch_product_l2s(pid, pg)

    changed = False

    for ip in incomplete_ignored:
        prod = product_by_id.get(ip.id.upper())
        if prod and not ip.name:
            ip.name = prod.name
            changed = True
        if not ip.url:
            pg = prod.price_group if prod else "00"
            ip.url = build_product_url(base, ip.id, pg)
            changed = True

    for wv in incomplete_variants:
        prod = product_by_id.get(wv.id.upper())

        if prod and not wv.name:
            wv.name = prod.name
            changed = True

        if not wv.url:
            wv.url = build_product_url(
                base, wv.id, wv.price_group, wv.color, wv.size,
            )
            changed = True

        if not wv.size_name and prod:
            wv.size_name = _find_size_name(prod, wv.size)
            changed = changed or bool(wv.size_name)

        if not wv.color_name:
            l2s = l2_by_product.get(wv.id.upper(), [])
            wv.color_name = _find_color_name(l2s, wv.color)
            changed = changed or bool(wv.color_name)

    if changed:
        logger.debug(
            "Enriched metadata for %d watched variant(s) "
            "and %d ignored product(s)",
            len(incomplete_variants), len(incomplete_ignored),
        )
    return changed

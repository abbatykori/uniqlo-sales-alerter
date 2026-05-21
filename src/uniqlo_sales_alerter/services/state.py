"""Seen-variant state management for new-deal detection.

Tracks which product variants have been seen so that only genuinely new
deals trigger notifications. State is persisted in the ``seen_variants``
SQLite table — replacing the pre-fork ``.seen_variants.json`` file. The
variant-key format is preserved (``product_id:color:size:discount`` or
``product_id:sale`` for items without a known discount) so the JSON-era
saved set transfers without translation if anyone copies it in via a
manual SQL bulk insert later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uniqlo_sales_alerter.db.models import SeenVariant
from uniqlo_sales_alerter.models.products import SaleItem, is_low_stock, parse_variant_codes

logger = logging.getLogger(__name__)


def _parse_variant_key(key: str) -> tuple[str, str, str, float | None]:
    """Split a variant key into its product / colour / size / discount components.

    Falls back to a degraded shape when the key was produced from a row without
    parseable variant codes (``product_id:suffix`` rather than the four-part form).
    """
    parts = key.split(":")
    if len(parts) == 4:
        product_id, color, size, suffix = parts
        try:
            discount: float | None = float(suffix)
        except ValueError:
            discount = None
        return product_id, color, size, discount
    if len(parts) == 2:
        product_id, suffix = parts
        try:
            discount = float(suffix)
        except ValueError:
            discount = None
        return product_id, "", "", discount
    logger.warning("Unexpected variant_key shape: %r", key)
    return key, "", "", None


class SeenVariantStore:
    """SQLite-backed seen-variant store.

    A variant key has the form ``product_id:color:size:discount`` and
    uniquely identifies a purchasable variant at a specific price point.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        suppress_low_stock: bool = False,
        low_stock_threshold: int = 0,
    ) -> None:
        self._session_factory = session_factory
        self._suppress_low_stock = suppress_low_stock
        self._low_stock_threshold = low_stock_threshold

    async def load(self) -> set[str]:
        """Return all variant keys currently in the ``seen_variants`` table."""
        async with self._session_factory() as session:
            result = await session.execute(select(SeenVariant.variant_key))
            keys = {row[0] for row in result.all()}
        logger.debug("Loaded %d seen variants from SQLite", len(keys))
        return keys

    async def save(self, variants: set[str]) -> None:
        """Replace the table contents with *variants* in a single transaction.

        Uses SQLite UPSERT to bump ``last_seen_at`` on existing rows and to
        insert new ones. Variants that were in the table but aren't in
        *variants* are deleted in the same transaction so the row count
        stays bounded.
        """
        now = datetime.now(timezone.utc)
        rows = []
        for key in variants:
            product_id, color, size, discount = _parse_variant_key(key)
            rows.append(
                {
                    "variant_key": key,
                    "product_id": product_id,
                    "color_code": color,
                    "size_code": size,
                    "discount_pct": discount,
                    "last_seen_at": now,
                }
            )

        async with self._session_factory() as session:
            async with session.begin():
                if variants:
                    stmt = sqlite_insert(SeenVariant).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[SeenVariant.variant_key],
                        set_={
                            "discount_pct": stmt.excluded.discount_pct,
                            "last_seen_at": stmt.excluded.last_seen_at,
                        },
                    )
                    await session.execute(stmt)
                await session.execute(
                    delete(SeenVariant).where(
                        SeenVariant.variant_key.notin_(variants) if variants
                        else SeenVariant.variant_key.is_not(None)
                    )
                )
        logger.debug("Persisted %d variant keys (deleted any missing)", len(variants))

    def variant_keys(self, item: SaleItem) -> set[str]:
        """Extract ``product_id:color:size:discount`` keys from a SaleItem.

        The discount percentage is appended so that a price change is
        detected as a new deal. For items without a known discount the
        literal ``"sale"`` is used instead.

        When :attr:`_suppress_low_stock` is True, low-stock variants are
        omitted from the returned set so they stay "unseen" — the user
        only gets alerted when stock climbs back above the threshold.
        """
        suffix = f"{item.discount_percentage:g}" if item.has_known_discount else "sale"

        keys: set[str] = set()
        saw_variant_url = False
        for idx, url in enumerate(item.product_urls):
            color, size = parse_variant_codes(url)
            if not (color and size):
                continue
            saw_variant_url = True
            if self._suppress_low_stock and self._variant_is_low(item, idx):
                continue
            keys.add(f"{item.product_id}:{color}:{size}:{suffix}")
        if not saw_variant_url:
            keys.add(f"{item.product_id}:{suffix}")
        return keys

    def find_new_deals(
        self, items: list[SaleItem], seen: set[str],
    ) -> list[SaleItem]:
        """Return items that have at least one variant not in *seen*."""
        return [
            item for item in items
            if self.variant_keys(item) - seen
        ]

    async def prune_older_than(self, days: int = 365) -> int:
        """Delete rows whose ``last_seen_at`` is older than *days*. Returns the row count."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    delete(SeenVariant).where(SeenVariant.last_seen_at < cutoff)
                )
        deleted = result.rowcount or 0
        logger.debug("Pruned %d seen_variants rows older than %d days", deleted, days)
        return deleted

    def _variant_is_low(self, item: SaleItem, idx: int) -> bool:
        """True when the variant at *idx* is currently in low-stock state."""
        variant = item.variant_at(idx)
        return is_low_stock(variant.quantity, variant.status, self._low_stock_threshold)

"""Shared fixtures for new-matcher / state / bridge-migration tests.

The session-scoped DB migration fixture lives in the top-level
``tests/conftest.py``; this conftest only adds per-test table cleanup
helpers.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from uniqlo_sales_alerter.db.engine import engine


@pytest.fixture(autouse=True)
def _clean_saved_filters_and_seen_variants():
    """Reset ``saved_filters`` and ``seen_variants`` between tests."""

    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))
            await conn.execute(text("DELETE FROM seen_variants"))

    asyncio.run(_truncate())
    yield

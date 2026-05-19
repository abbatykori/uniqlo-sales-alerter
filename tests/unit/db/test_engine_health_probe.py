"""Health probe correctness — happy path and the failure fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from uniqlo_sales_alerter.db.engine import health_probe


@pytest.mark.asyncio
async def test_health_probe_returns_true_against_writeable_db() -> None:
    assert await health_probe() is True


@pytest.mark.asyncio
async def test_health_probe_returns_false_when_write_raises() -> None:
    """When the underlying engine raises on connect, the probe must return False."""
    from sqlalchemy.exc import OperationalError

    with patch("uniqlo_sales_alerter.db.engine.engine") as mock_engine:
        mock_engine.begin.side_effect = OperationalError("simulated", None, Exception())
        result = await health_probe()

    assert result is False

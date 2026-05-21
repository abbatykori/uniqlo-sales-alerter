"""/ui/insights renders the heatmap or the insufficient-data banner."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import DealObservation
from uniqlo_sales_alerter.services.heatmap import INSUFFICIENT_DATA_DAYS


@pytest.fixture(autouse=True)
def _clean_observations():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM deal_observations"))

    asyncio.run(_truncate())
    yield


async def _seed(*, days: int, hits_per_day: int = 1) -> None:
    rows = []
    for d in range(days):
        for _ in range(hits_per_day):
            when = (datetime.now(timezone.utc) - timedelta(days=d)).replace(
                hour=12, minute=0, second=0, microsecond=0, tzinfo=None,
            )
            rows.append(
                DealObservation(
                    observed_at=when, product_id="E001",
                    discount_pct=60.0, is_deep=1,
                )
            )
    async with async_session_factory() as session:
        async with session.begin():
            session.add_all(rows)


def test_insights_renders_insufficient_data_banner(client):
    asyncio.run(_seed(days=5))
    r = client.get("/ui/insights")
    assert r.status_code == 200
    assert "Heatmap will activate" in r.text
    assert "Currently: 5 days" in r.text


def test_insights_renders_grid_when_sufficient(client):
    asyncio.run(_seed(days=INSUFFICIENT_DATA_DAYS, hits_per_day=2))
    r = client.get("/ui/insights")
    assert r.status_code == 200
    assert "Heatmap will activate" not in r.text
    # 7 day labels in the row headers
    for label in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        assert label in r.text
    # 24 hour columns rendered as zero-padded headers
    for hour_str in ("00", "12", "23"):
        assert hour_str in r.text


def test_insights_lookback_param_respected(client):
    """A 30-day lookback should display the same shape but use the requested window."""
    asyncio.run(_seed(days=5))
    r = client.get("/ui/insights?lookback=30")
    assert r.status_code == 200
    assert "last 30 days" in r.text


def test_insights_renders_all_168_cells(client):
    asyncio.run(_seed(days=INSUFFICIENT_DATA_DAYS))
    r = client.get("/ui/insights")
    assert r.status_code == 200
    # Each cell is a <td> with title=... and rgba background
    assert r.text.count("rgba(194,165,109,") == 7 * 24

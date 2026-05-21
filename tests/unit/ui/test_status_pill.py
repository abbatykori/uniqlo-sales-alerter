"""/ui/status-pill returns the right counts + freshness label."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import SavedFilter


@pytest.fixture(autouse=True)
def _clean_saved_filters():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))

    asyncio.run(_truncate())
    yield


async def _insert(name: str, *, snooze_until=None, enabled: int = 1) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            session.add(SavedFilter(
                name=name,
                gender=[], min_discount=0.0,
                sizes_clothing=[], sizes_pants=[], sizes_shoes=[],
                one_size_match=0, availability_mode="both",
                ignored_keywords=[],
                enabled=enabled,
                snooze_until=snooze_until,
            ))


def test_status_pill_empty_state(client):
    r = client.get("/ui/status-pill")
    assert r.status_code == 200
    assert "no check yet" in r.text
    assert "0 active" in r.text
    assert "0 snoozed" in r.text


def test_status_pill_counts_active_and_snoozed(client):
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    asyncio.run(_insert("Active1"))
    asyncio.run(_insert("Active2"))
    asyncio.run(_insert("Snoozed", snooze_until=naive_now + timedelta(days=3)))
    # Disabled filters don't count
    asyncio.run(_insert("Disabled", enabled=0))

    r = client.get("/ui/status-pill")
    assert r.status_code == 200
    assert "2 active" in r.text
    assert "1 snoozed" in r.text


def test_status_pill_shows_last_check_age(client):
    """Set app_state.last_check_at and verify the freshness label."""
    from uniqlo_sales_alerter.main import app

    app.state.app_state.last_check_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    r = client.get("/ui/status-pill")
    assert r.status_code == 200
    assert "15 min ago" in r.text or "14 min ago" in r.text


def test_base_shell_includes_status_pill_polling(client):
    r = client.get("/ui/filters")
    assert r.status_code == 200
    assert 'hx-get="/ui/status-pill"' in r.text
    assert "every 30s" in r.text

"""Deals view + Inbox view + Help index."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import NotificationLog, SavedFilter


@pytest.fixture(autouse=True)
def _clean_tables():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))
            await conn.execute(text("DELETE FROM notification_log"))

    asyncio.run(_truncate())
    yield


def test_deals_view_first_run_empty_state(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Watch Uniqlo sales in your sizes" in r.text
    assert "Add my first filter" in r.text
    assert "Paste a recent invoice" in r.text


def test_deals_view_no_match_state_when_filters_exist(client):
    async def _seed():
        async with async_session_factory() as session:
            async with session.begin():
                session.add(SavedFilter(
                    name="X", gender=[], min_discount=0.0,
                    sizes_clothing=[], sizes_pants=[], sizes_shoes=[],
                    one_size_match=0, availability_mode="both",
                    ignored_keywords=[], enabled=1,
                ))

    asyncio.run(_seed())
    r = client.get("/")
    assert r.status_code == 200
    assert "Nothing matched today" in r.text


def test_inbox_view_empty_state(client):
    r = client.get("/inbox")
    assert r.status_code == 200
    assert "Notifications will appear here" in r.text


def test_inbox_view_renders_recent_dispatches(client):
    async def _seed():
        async with async_session_factory() as session:
            async with session.begin():
                session.add(NotificationLog(
                    sent_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    channel="apprise",
                    filter_ids=[1, 2],
                    deal_count=3,
                    status="success",
                ))

    asyncio.run(_seed())
    r = client.get("/inbox")
    assert r.status_code == 200
    assert "apprise" in r.text
    assert ">3<" in r.text
    assert "success" in r.text


def test_help_index_lists_diataxis_categories(client):
    r = client.get("/help")
    assert r.status_code == 200
    for label in ("Tutorials", "How-to", "Reference", "Explanation"):
        assert label in r.text

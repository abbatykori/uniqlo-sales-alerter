"""AppriseNotifier — dispatch shell, notification_log writes, filter-name lookup."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from tests.conftest import sample_deal
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import NotificationLog, SavedFilter
from uniqlo_sales_alerter.notifications.apprise_notifier import AppriseNotifier


@pytest.fixture(autouse=True)
def _clean_tables():
    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM notification_log"))
            await conn.execute(text("DELETE FROM saved_filters"))

    asyncio.run(_truncate())
    yield


async def _insert_filter(name: str) -> int:
    row = SavedFilter(
        name=name,
        gender=[],
        min_discount=0.0,
        sizes_clothing=[], sizes_pants=[], sizes_shoes=[],
        one_size_match=0,
        availability_mode="both",
        ignored_keywords=[],
        enabled=1,
    )
    async with async_session_factory() as session:
        async with session.begin():
            session.add(row)
        await session.refresh(row)
        return row.id


def test_disabled_with_no_urls() -> None:
    n = AppriseNotifier([])
    assert n.is_enabled() is False


def test_enabled_with_urls() -> None:
    n = AppriseNotifier(["json://localhost:1234"])
    assert n.is_enabled() is True


@pytest.mark.asyncio
async def test_send_logs_success_row() -> None:
    n = AppriseNotifier(["json://localhost:9999"])
    deals = [sample_deal(product_id="E001")]
    with patch.object(n, "_dispatch_via_apprise", return_value=True) as mock_dispatch:
        await n.send(deals)
    mock_dispatch.assert_awaited_once()

    async with async_session_factory() as session:
        rows = (await session.execute(select(NotificationLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].channel == "apprise"
    assert rows[0].status == "success"
    assert rows[0].deal_count == 1
    assert rows[0].error is None


@pytest.mark.asyncio
async def test_send_logs_failure_row_when_apprise_returns_false() -> None:
    n = AppriseNotifier(["json://broken"])
    with patch.object(n, "_dispatch_via_apprise", return_value=False):
        await n.send([sample_deal()])

    async with async_session_factory() as session:
        row = (await session.execute(select(NotificationLog))).scalar_one()
    assert row.status == "failed"
    assert row.error is not None


@pytest.mark.asyncio
async def test_send_skips_when_no_deals() -> None:
    n = AppriseNotifier(["json://localhost"])
    with patch.object(n, "_dispatch_via_apprise") as mock_dispatch:
        await n.send([])
    mock_dispatch.assert_not_called()
    async with async_session_factory() as session:
        rows = (await session.execute(select(NotificationLog))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_send_skips_when_no_urls_even_with_deals() -> None:
    n = AppriseNotifier([])
    with patch.object(n, "_dispatch_via_apprise") as mock_dispatch:
        await n.send([sample_deal()])
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_filter_ids_aggregated_across_deals() -> None:
    a = await _insert_filter("A")
    b = await _insert_filter("B")
    deals = [
        sample_deal(product_id="E001", matched_filter_ids=[a]),
        sample_deal(product_id="E002", matched_filter_ids=[a, b]),
    ]
    n = AppriseNotifier(["json://localhost"])
    with patch.object(n, "_dispatch_via_apprise", return_value=True):
        await n.send(deals)

    async with async_session_factory() as session:
        row = (await session.execute(select(NotificationLog))).scalar_one()
    assert row.filter_ids == sorted([a, b])


@pytest.mark.asyncio
async def test_filter_names_appear_in_html_body() -> None:
    a = await _insert_filter("Me tops")
    n = AppriseNotifier(["json://localhost"])
    deal = sample_deal(product_id="E001", name="Soft Tee", matched_filter_ids=[a])

    captured: dict[str, str] = {}

    async def _capture(title, html_body, text_body):
        captured.update(title=title, html=html_body, text=text_body)
        return True

    with patch.object(n, "_dispatch_via_apprise", side_effect=_capture):
        await n.send([deal])

    assert "Me tops" in captured["html"]
    assert "Soft Tee" in captured["html"]
    assert "Me tops" in captured["text"]


@pytest.mark.asyncio
async def test_watched_deal_gets_watched_tag() -> None:
    n = AppriseNotifier(["json://localhost"])
    deal = sample_deal(product_id="E001", is_watched=True, matched_filter_ids=[])
    captured: dict[str, str] = {}

    async def _capture(title, html_body, text_body):
        captured.update(html=html_body, text=text_body)
        return True

    with patch.object(n, "_dispatch_via_apprise", side_effect=_capture):
        await n.send([deal])

    assert "Watched" in captured["html"]


@pytest.mark.asyncio
async def test_title_includes_deal_count() -> None:
    n = AppriseNotifier(["json://localhost"])
    captured: dict[str, str] = {}

    async def _capture(title, html_body, text_body):
        captured["title"] = title
        return True

    with patch.object(n, "_dispatch_via_apprise", side_effect=_capture):
        await n.send([sample_deal(product_id="E001"), sample_deal(product_id="E002")])

    assert "2" in captured["title"]
    assert "Uniqlo" in captured["title"]

"""Signed /actions/* handlers — verification, snooze, tamper rejection."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.db.engine import async_session_factory, engine
from uniqlo_sales_alerter.db.models import SavedFilter
from uniqlo_sales_alerter.notifications.action_urls import sign_action
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker

_SECRET = "test-secret-for-action-handlers-3456"


@pytest.fixture(autouse=True)
def _clean_saved_filters():
    async def _truncate():
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))

    asyncio.run(_truncate())
    yield


@pytest.fixture()
def client():
    from uniqlo_sales_alerter.main import AppState, app

    config = AppConfig()
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=MagicMock(running=True),
        secret=_SECRET,
    )
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app)


def _signed(action: str, *, path_arg: str = "", payload: dict | None = None) -> str:
    full = sign_action(
        secret=_SECRET,
        base_url="http://testserver",
        action=action,
        path_arg=path_arg,
        payload=payload or {},
    )
    return full.replace("http://testserver", "", 1)


async def _insert_filter(name: str = "Test") -> int:
    row = SavedFilter(
        name=name,
        gender=[], min_discount=0.0,
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


# --- Snooze handler --------------------------------------------------------


def test_snooze_1d_sets_snooze_until_about_one_day_out(client: TestClient):
    filter_id = asyncio.run(_insert_filter("Daily"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "1d"})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "snoozed" in resp.text.lower()

    async def _read():
        async with async_session_factory() as session:
            return await session.get(SavedFilter, filter_id)

    row = asyncio.run(_read())
    assert row.snooze_until is not None
    # Within ~24h of now
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert timedelta(hours=23) <= row.snooze_until - naive_now <= timedelta(hours=25)


def test_snooze_7d_persists_seven_days_out(client: TestClient):
    filter_id = asyncio.run(_insert_filter("Weekly"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "7d"})
    resp = client.get(url)
    assert resp.status_code == 200

    async def _read():
        async with async_session_factory() as session:
            return await session.get(SavedFilter, filter_id)

    row = asyncio.run(_read())
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert timedelta(days=6, hours=23) <= row.snooze_until - naive_now <= timedelta(days=7, hours=1)


def test_snooze_forever_uses_year_9999_sentinel(client: TestClient):
    filter_id = asyncio.run(_insert_filter("Forever"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "forever"})
    resp = client.get(url)
    assert resp.status_code == 200

    async def _read():
        async with async_session_factory() as session:
            return await session.get(SavedFilter, filter_id)

    row = asyncio.run(_read())
    assert row.snooze_until.year == 9999


def test_snooze_invalid_duration_returns_friendly_message(client: TestClient):
    filter_id = asyncio.run(_insert_filter("X"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "10y"})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "invalid" in resp.text.lower() or "unsupported" in resp.text.lower()


def test_snooze_missing_filter_returns_not_found_page(client: TestClient):
    url = _signed("snooze", payload={"filter_id": "9999", "duration": "1d"})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()


def test_snooze_is_idempotent(client: TestClient):
    """Re-applying the same snooze URL just extends the expiry."""
    filter_id = asyncio.run(_insert_filter("Idempotent"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "7d"})
    r1 = client.get(url)
    r2 = client.get(url)
    assert r1.status_code == r2.status_code == 200


# --- Signature enforcement on existing handlers ----------------------------


def test_unsigned_snooze_url_rejected(client: TestClient):
    resp = client.get("/actions/snooze?filter_id=1&duration=7d")
    assert resp.status_code == 403


def test_unsigned_ignore_url_rejected(client: TestClient):
    resp = client.get("/actions/ignore/E001?name=Test")
    assert resp.status_code == 403


def test_unsigned_watch_url_rejected(client: TestClient):
    resp = client.get("/actions/watch/E001?name=Test")
    assert resp.status_code == 403


def test_tampered_payload_rejected(client: TestClient):
    """Modifying the payload after signing must invalidate the signature."""
    filter_id = asyncio.run(_insert_filter("Tamper"))
    url = _signed("snooze", payload={"filter_id": str(filter_id), "duration": "1d"})
    # Tamper: bump the duration without re-signing
    tampered = url.replace("duration=1d", "duration=forever")
    resp = client.get(tampered)
    assert resp.status_code == 403


def test_expired_url_returns_410(client: TestClient):
    """An expired URL must return 410 Gone, not 403 — different actionable
    state for the user."""
    filter_id = asyncio.run(_insert_filter("Expired"))
    past = datetime.now(timezone.utc) - timedelta(days=400)
    full = sign_action(
        secret=_SECRET,
        base_url="http://testserver",
        action="snooze",
        payload={"filter_id": str(filter_id), "duration": "1d"},
        now=past,
        ttl_days=30,
    )
    url = full.replace("http://testserver", "", 1)
    resp = client.get(url)
    assert resp.status_code == 410

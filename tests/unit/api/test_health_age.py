"""/health populates last_check_age_seconds + last_check_fresh from app_state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


def _build_app_state(*, last_check_at, interval_minutes: int = 30):
    from uniqlo_sales_alerter.main import AppState, app

    config = AppConfig.model_validate(
        {"uniqlo": {"country": "nl/nl", "check_interval_minutes": interval_minutes}}
    )
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=MagicMock(running=True),
        last_check_at=last_check_at,
    )
    app.router.lifespan_context = None  # type: ignore[assignment]
    return app


def test_fresh_check_reports_short_age_and_ok_status():
    app = _build_app_state(last_check_at=datetime.now(timezone.utc), interval_minutes=30)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["last_check_age_seconds"] is not None
    assert body["last_check_age_seconds"] < 5
    assert body["last_check_fresh"] is True


def test_stale_check_degrades_to_503():
    # 90 minutes ago with interval=30 (stale threshold = 60 minutes)
    stale = datetime.now(timezone.utc) - timedelta(minutes=90)
    app = _build_app_state(last_check_at=stale, interval_minutes=30)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["last_check_age_seconds"] >= 90 * 60
    assert body["last_check_fresh"] is False


def test_within_threshold_stays_ok():
    # 45 minutes ago with interval=30 (threshold = 60); just under stale.
    recent = datetime.now(timezone.utc) - timedelta(minutes=45)
    app = _build_app_state(last_check_at=recent, interval_minutes=30)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json()["last_check_fresh"] is True


def test_no_check_yet_returns_null_age_and_does_not_degrade():
    app = _build_app_state(last_check_at=None, interval_minutes=30)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_check_age_seconds"] is None
    assert body["last_check_fresh"] is None


def test_zero_interval_skips_freshness_check():
    """check_interval_minutes=0 means periodic checks disabled; freshness is None."""
    app = _build_app_state(
        last_check_at=datetime.now(timezone.utc) - timedelta(hours=10),
        interval_minutes=0,
    )
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_check_age_seconds"] is not None
    assert body["last_check_fresh"] is None


def test_naive_datetime_treated_as_utc():
    """Sqlite returns naive timestamps. Health endpoint must coerce them to UTC."""
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    app = _build_app_state(last_check_at=naive_now, interval_minutes=30)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_check_age_seconds"] is not None
    assert body["last_check_age_seconds"] < 5

"""Healthcheck endpoint — degraded paths and edge cases.

The happy path is covered in ``tests/test_api.py::TestHealthEndpoint``. This
module focuses on the degraded scenarios that flip the response to 503.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


@pytest.fixture()
def app_with_state():
    """Yield the FastAPI app with a fresh ``app_state``. Caller assigns the scheduler."""
    from uniqlo_sales_alerter.main import AppState, app

    config = AppConfig()
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=MagicMock(running=False),
    )
    app.router.lifespan_context = None  # type: ignore[assignment]
    yield app


def test_health_degraded_when_scheduler_not_running(app_with_state):
    client = TestClient(app_with_state)
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["scheduler_running"] is False
    assert body["message"] == "Degraded"


def test_health_scheduler_field_none_when_app_state_missing(app_with_state):
    """If no app_state has been wired, the scheduler field reports ``None`` not ``False``."""
    if hasattr(app_with_state.state, "app_state"):
        delattr(app_with_state.state, "app_state")
    client = TestClient(app_with_state)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheduler_running"] is None
    assert body["status"] == "ok"

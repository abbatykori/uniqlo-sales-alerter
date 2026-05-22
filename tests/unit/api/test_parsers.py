"""POST /api/v1/parsers/invoice and the HTMX /filters/paste flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


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
    )
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app)


_NL_FIXTURE = """\
47492809120000, Track Joggers
BLACK, 5-6 Years (120cm)
Price: 1 x 9,90€
46932256006000, AIRism Cotton T-Shirt
OLIVE, XL
Price: 1 x 12,90€
"""


def test_rest_invoice_parse_returns_categorised_sizes(client):
    r = client.post("/api/v1/parsers/invoice", json={"text": _NL_FIXTURE})
    assert r.status_code == 200
    body = r.json()
    assert body["clothing"] == ["XL"]
    assert body["kids"] == ["120cm"]
    assert body["product_ids"] == ["47492809120000", "46932256006000"]


def test_rest_invoice_parse_empty_body_returns_422(client):
    r = client.post("/api/v1/parsers/invoice", json={"text": ""})
    assert r.status_code == 422


def test_ui_paste_form_renders(client):
    r = client.get("/filters/paste")
    assert r.status_code == 200
    assert "<textarea" in r.text
    assert 'name="text"' in r.text


def test_ui_paste_post_returns_chip_suggestions(client):
    r = client.post("/filters/paste", data={"text": _NL_FIXTURE})
    assert r.status_code == 200
    assert "120cm" in r.text
    assert "XL" in r.text
    assert "Clothing:" in r.text
    assert "Kids:" in r.text


def test_ui_paste_post_empty_text_shows_friendly_message(client):
    r = client.post("/filters/paste", data={"text": ""})
    assert r.status_code == 200
    assert "No detectable sizes" in r.text


def test_ui_paste_post_with_garbage_explains(client):
    r = client.post("/filters/paste", data={"text": "Hello there"})
    assert r.status_code == 200
    assert "No sizes detected" in r.text

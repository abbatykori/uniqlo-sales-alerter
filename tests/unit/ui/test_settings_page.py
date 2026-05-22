"""Settings page — v2.1 Tailwind rewrite of the legacy ``settings_ui.py``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_disk_writes(tmp_path: Path):
    """Don't let settings POSTs persist over the user's real config.yaml."""
    with (
        patch("uniqlo_sales_alerter.ui.routes._persist_config") as persist,
    ):
        async def _no_op(*args, **kwargs):
            return None

        persist.side_effect = _no_op
        yield


def test_settings_page_renders_top_level_sections(client) -> None:
    response = client.get("/settings")
    assert response.status_code == 200
    for heading in (
        "Notifications",
        "Schedule",
        "Store country",
        "Watched variants",
        "Ignored items",
    ):
        assert heading in response.text


def test_settings_page_lists_existing_apprise_urls(client) -> None:
    state = client.app.state.app_state
    state.config.notifications.apprise_urls = ["tgram://abc/123", "mailto://x@y.z"]
    response = client.get("/settings")
    assert "tgram://abc/123" in response.text
    assert "mailto://x@y.z" in response.text


def test_post_apprise_appends_url(client) -> None:
    state = client.app.state.app_state
    state.config.notifications.apprise_urls = []
    response = client.post("/settings/apprise", data={"url": "tgram://NEW/999"})
    assert response.status_code == 200
    assert "tgram://NEW/999" in response.text
    assert state.config.notifications.apprise_urls == ["tgram://NEW/999"]


def test_post_apprise_skips_duplicates(client) -> None:
    state = client.app.state.app_state
    state.config.notifications.apprise_urls = ["tgram://abc/123"]
    response = client.post("/settings/apprise", data={"url": "tgram://abc/123"})
    assert response.status_code == 200
    assert state.config.notifications.apprise_urls == ["tgram://abc/123"]


def test_delete_apprise_removes_by_index(client) -> None:
    state = client.app.state.app_state
    state.config.notifications.apprise_urls = ["one", "two", "three"]
    response = client.delete("/settings/apprise/1")
    assert response.status_code == 200
    assert state.config.notifications.apprise_urls == ["one", "three"]


def test_apprise_test_unknown_index_returns_404(client) -> None:
    state = client.app.state.app_state
    state.config.notifications.apprise_urls = []
    response = client.post("/settings/apprise/0/test")
    assert response.status_code == 404


def test_post_schedule_updates_intervals(client) -> None:
    state = client.app.state.app_state
    response = client.post(
        "/settings/schedule",
        data={
            "check_interval_minutes": "15",
            "scheduled_checks": "08:00, 18:00",
            "quiet_enabled": "true",
            "quiet_start": "00:30",
            "quiet_end": "07:30",
        },
    )
    assert response.status_code == 200
    assert state.config.uniqlo.check_interval_minutes == 15
    assert state.config.uniqlo.scheduled_checks == ["08:00", "18:00"]
    assert state.config.quiet_hours.enabled is True


def test_post_country_updates_store_country(client) -> None:
    state = client.app.state.app_state
    response = client.post(
        "/settings/country",
        data={"store_country": "UK", "ui_language": "en"},
    )
    assert response.status_code == 200
    assert state.config.store_country == "uk"
    assert state.config.ui_language == "en"


def test_post_ignored_keyword_appends(client) -> None:
    state = client.app.state.app_state
    state.config.filters.ignored_keywords = ["paisley"]
    response = client.post(
        "/settings/ignored/keywords", data={"keyword": "Oversized"}
    )
    assert response.status_code == 200
    assert state.config.filters.ignored_keywords == ["paisley", "oversized"]


def test_delete_ignored_keyword_by_index(client) -> None:
    state = client.app.state.app_state
    state.config.filters.ignored_keywords = ["a", "b", "c"]
    response = client.delete("/settings/ignored/keywords/1")
    assert response.status_code == 200
    assert state.config.filters.ignored_keywords == ["a", "c"]


def test_legacy_settings_ui_module_is_gone() -> None:
    """The 1,308-line inline-HTML editor is removed in v2.1."""
    import importlib.util

    spec = importlib.util.find_spec("uniqlo_sales_alerter.settings_ui")
    assert spec is None, "settings_ui module should no longer exist"

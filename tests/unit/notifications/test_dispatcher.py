"""NotificationDispatcher: URL aggregation + single-notifier dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import sample_deal
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher


def test_no_urls_when_config_default() -> None:
    d = NotificationDispatcher(AppConfig())
    assert d.urls == []
    assert d.notifier.is_enabled() is False


def test_aggregates_explicit_urls_and_legacy_translations() -> None:
    cfg = AppConfig.model_validate({
        "notifications": {
            "apprise_urls": ["ntfy://example.com/topic"],
            "channels": {
                "telegram": {"enabled": True, "bot_token": "BOT", "chat_id": "9"},
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "use_tls": True,
                    "smtp_user": "u",
                    "smtp_password": "p",
                    "from_address": "u@example.com",
                    "to_addresses": ["t@example.com"],
                },
            },
        }
    })
    d = NotificationDispatcher(cfg)
    assert any(u.startswith("ntfy://") for u in d.urls)
    assert any(u.startswith("tgram://") for u in d.urls)
    assert any(u.startswith("mailto://") for u in d.urls)
    assert len(d.urls) == 3


def test_legacy_blocks_disabled_does_not_emit_urls() -> None:
    """Disabling legacy channels means only apprise_urls remain."""
    cfg = AppConfig.model_validate({
        "notifications": {
            "apprise_urls": ["json://localhost:1234"],
            "channels": {
                "telegram": {"enabled": False, "bot_token": "X", "chat_id": "Y"},
                "email": {"enabled": False},
            },
        }
    })
    d = NotificationDispatcher(cfg)
    assert d.urls == ["json://localhost:1234"]


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_deals() -> None:
    d = NotificationDispatcher(AppConfig())
    with patch.object(d.notifier, "send", new=AsyncMock()) as mock_send:
        await d.dispatch([])
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_skips_when_notifier_disabled() -> None:
    """An empty URL list means the dispatcher must NOT call send (and not log to DB)."""
    d = NotificationDispatcher(AppConfig())
    with patch.object(d.notifier, "send", new=AsyncMock()) as mock_send:
        await d.dispatch([sample_deal()])
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_calls_notifier_send_when_enabled() -> None:
    cfg = AppConfig.model_validate(
        {"notifications": {"apprise_urls": ["json://localhost:9999"]}}
    )
    d = NotificationDispatcher(cfg)
    with patch.object(d.notifier, "send", new=AsyncMock()) as mock_send:
        await d.dispatch([sample_deal()])
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_swallows_exceptions() -> None:
    """A failing notifier must not propagate; the scheduler keeps running."""
    cfg = AppConfig.model_validate(
        {"notifications": {"apprise_urls": ["json://localhost"]}}
    )
    d = NotificationDispatcher(cfg)
    with patch.object(d.notifier, "send", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await d.dispatch([sample_deal()])  # should not raise

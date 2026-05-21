"""Legacy channels.{telegram,email} → Apprise URL translation."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from uniqlo_sales_alerter.config import NotificationConfig
from uniqlo_sales_alerter.notifications.url_translation import (
    legacy_channels_to_apprise_urls,
)


def _notif(**channel_overrides) -> NotificationConfig:
    return NotificationConfig.model_validate({"channels": channel_overrides})


def test_no_translation_when_blocks_disabled() -> None:
    assert legacy_channels_to_apprise_urls(NotificationConfig()) == []


def test_telegram_enabled_translates_to_tgram() -> None:
    cfg = _notif(telegram={"enabled": True, "bot_token": "BOT", "chat_id": "123"})
    urls = legacy_channels_to_apprise_urls(cfg)
    assert urls == ["tgram://BOT/123"]


def test_telegram_skipped_when_missing_credentials() -> None:
    cfg = _notif(telegram={"enabled": True, "bot_token": "", "chat_id": "123"})
    assert legacy_channels_to_apprise_urls(cfg) == []


def test_email_starttls_587_omits_port_segment() -> None:
    """Apprise treats 587 as the implicit STARTTLS port; we don't emit a :port segment."""
    cfg = _notif(email={
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True,
        "smtp_user": "alice@example.com",
        "smtp_password": "p@ss/word",
        "from_address": "alice@example.com",
        "to_addresses": ["bob@example.com"],
    })
    url = legacy_channels_to_apprise_urls(cfg)[0]
    assert url.startswith("mailto://")
    # Password URL-encoded — '/' must become %2F, '@' stays
    assert "p%40ss%2Fword" in url
    parts = urlparse(url)
    # No explicit port in netloc since 587 is implicit
    assert ":587" not in parts.netloc
    qs = parse_qs(parts.query)
    assert qs["to"] == ["bob@example.com"]
    assert qs["from"] == ["alice@example.com"]
    assert qs["secure"] == ["yes"]


def test_email_implicit_tls_465() -> None:
    cfg = _notif(email={
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "use_tls": True,
        "smtp_user": "u",
        "smtp_password": "p",
        "from_address": "u@example.com",
        "to_addresses": ["t@example.com"],
    })
    url = legacy_channels_to_apprise_urls(cfg)[0]
    assert ":465" not in url  # 465 is implicit in Apprise's mailto: handler


def test_email_custom_port_included() -> None:
    cfg = _notif(email={
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
        "use_tls": False,
        "smtp_user": "u",
        "smtp_password": "p",
        "from_address": "u@example.com",
        "to_addresses": ["t@example.com"],
    })
    url = legacy_channels_to_apprise_urls(cfg)[0]
    assert ":2525" in url
    assert "secure=no" in url


def test_email_multiple_recipients_comma_joined() -> None:
    cfg = _notif(email={
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True,
        "smtp_user": "u",
        "smtp_password": "p",
        "from_address": "u@example.com",
        "to_addresses": ["one@example.com", "two@example.com"],
    })
    url = legacy_channels_to_apprise_urls(cfg)[0]
    qs = parse_qs(urlparse(url).query)
    assert qs["to"] == ["one@example.com,two@example.com"]


def test_email_skipped_when_to_addresses_empty() -> None:
    cfg = _notif(email={
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "from_address": "u@example.com",
        "to_addresses": [],
    })
    assert legacy_channels_to_apprise_urls(cfg) == []


def test_both_blocks_enabled_produces_two_urls() -> None:
    cfg = _notif(
        telegram={"enabled": True, "bot_token": "TOK", "chat_id": "42"},
        email={
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "use_tls": True,
            "smtp_user": "u",
            "smtp_password": "p",
            "from_address": "u@example.com",
            "to_addresses": ["t@example.com"],
        },
    )
    urls = legacy_channels_to_apprise_urls(cfg)
    assert len(urls) == 2
    assert any(u.startswith("tgram://") for u in urls)
    assert any(u.startswith("mailto://") for u in urls)

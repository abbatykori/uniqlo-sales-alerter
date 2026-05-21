"""NotificationConfig.apprise_urls + NOTIFICATIONS_APPRISE_URLS env var."""

from __future__ import annotations

from uniqlo_sales_alerter.config import AppConfig, _config_from_env


def test_default_apprise_urls_empty() -> None:
    cfg = AppConfig()
    assert cfg.notifications.apprise_urls == []


def test_apprise_urls_from_yaml() -> None:
    cfg = AppConfig.model_validate(
        {"notifications": {"apprise_urls": ["tgram://abc/123", "mailto://u:p@x.com"]}}
    )
    assert cfg.notifications.apprise_urls == ["tgram://abc/123", "mailto://u:p@x.com"]


def test_env_var_overrides_via_comma_split(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATIONS_APPRISE_URLS", "tgram://one, ntfy://two")
    overrides = _config_from_env()
    assert overrides["notifications"]["apprise_urls"] == ["tgram://one", "ntfy://two"]


def test_dispatcher_registers_apprise_notifier_only_when_urls_set() -> None:
    from uniqlo_sales_alerter.notifications.apprise_notifier import AppriseNotifier
    from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher

    empty = NotificationDispatcher(AppConfig())
    assert not any(isinstance(n, AppriseNotifier) for n in empty._notifiers)

    with_urls = NotificationDispatcher(
        AppConfig.model_validate(
            {"notifications": {"apprise_urls": ["json://localhost:1234"]}}
        )
    )
    assert any(isinstance(n, AppriseNotifier) for n in with_urls._notifiers)

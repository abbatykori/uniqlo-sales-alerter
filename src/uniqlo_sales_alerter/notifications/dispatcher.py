"""Notification dispatcher — routes all alerts through a single AppriseNotifier.

The pre-fork code maintained four hand-rolled notifiers (Telegram, Email,
Console, HTML report) registered side by side. PR-D collapses them to one
:class:`AppriseNotifier`. URLs come from two sources concatenated:

1. ``config.notifications.apprise_urls`` — explicit Apprise URLs the user has
   configured (~80 services supported).
2. The legacy ``channels.telegram`` / ``channels.email`` blocks, translated by
   :func:`legacy_channels_to_apprise_urls` into ``tgram://...`` / ``mailto://...``
   so existing single-user installs keep working without manual reconfiguration.

The ``preview_cli`` and ``preview_html`` config toggles are no-ops for the
dispatch loop after PR-D. The legacy ``console.py`` and ``html_report.py``
modules remain in the tree for the ``--preview-cli`` / ``--preview-html`` CLI
flags in ``__main__.py`` only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.apprise_notifier import AppriseNotifier
from uniqlo_sales_alerter.notifications.url_translation import (
    legacy_channels_to_apprise_urls,
)

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import AppConfig

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Routes deals to a single Apprise notifier covering all configured URLs."""

    def __init__(self, config: AppConfig, *, secret: str = "") -> None:
        self._config = config
        urls = list(config.notifications.apprise_urls) + legacy_channels_to_apprise_urls(
            config.notifications,
        )
        self._notifier = AppriseNotifier(
            urls,
            server_url=config.full_server_url,
            low_stock_threshold=config.notifications.low_stock_threshold,
            secret=secret,
        )
        logger.info(
            "NotificationDispatcher: %d Apprise URL(s) configured", len(urls)
        )

    @property
    def urls(self) -> list[str]:
        """The full URL set the notifier will dispatch to."""
        return list(self._notifier._urls)

    @property
    def notifier(self) -> AppriseNotifier:
        return self._notifier

    async def dispatch(self, deals: list[SaleItem]) -> None:
        """Send *deals* via Apprise. No-op if no URLs are configured."""
        if not deals:
            logger.debug("No deals to dispatch — skipping")
            return
        if not self._notifier.is_enabled():
            logger.info(
                "No Apprise URLs configured — %d deal(s) not dispatched",
                len(deals),
            )
            return
        try:
            await self._notifier.send(deals)
            logger.info("Dispatched %d deal(s) via Apprise", len(deals))
        except Exception:
            logger.exception("Apprise dispatch failed")

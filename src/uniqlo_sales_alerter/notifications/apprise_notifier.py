"""Apprise-based notifier — single channel covering ~80 services.

PR-B (this file) ships the dispatcher shell:

- accepts a list of Apprise URLs
- renders a *placeholder* HTML body + plaintext body + title
- delegates the network send to :class:`apprise.Apprise` in a worker
  thread (since Apprise is sync)
- logs one row to ``notification_log`` per dispatch (success or failure)

PR-C will replace the placeholder rendering with Jinja templates that
surface ``matched_filter_ids`` as filter-name chips, the watched badge,
per-variant URLs, and low-stock styling.

PR-D will retire the legacy four-channel notifiers and route both the
explicit ``notifications.apprise_urls`` config and the translated
``channels.telegram``/``channels.email`` URLs through this notifier.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import apprise
from sqlalchemy import select

from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import NotificationLog, SavedFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from uniqlo_sales_alerter.models.products import SaleItem

logger = logging.getLogger(__name__)


class AppriseNotifier:
    """Dispatch deals to a list of Apprise URLs and log to ``notification_log``."""

    def __init__(
        self,
        urls: list[str],
        *,
        session_factory: "async_sessionmaker | None" = None,
        server_url: str = "",
        low_stock_threshold: int = 0,
    ) -> None:
        self._urls = [u for u in urls if u]
        self._session_factory = session_factory or async_session_factory
        self._server_url = server_url
        self._low_stock_threshold = low_stock_threshold

    def is_enabled(self) -> bool:
        return bool(self._urls)

    async def send(self, deals: list["SaleItem"]) -> None:
        if not deals or not self._urls:
            return

        filter_ids = sorted({fid for d in deals for fid in d.matched_filter_ids})
        names_by_id = await self._fetch_filter_names(filter_ids)

        title = self._render_title(deals)
        html_body = self._render_html(deals, names_by_id)
        text_body = self._render_text(deals, names_by_id)

        success = await self._dispatch_via_apprise(title, html_body, text_body)
        await self._log_dispatch(deals, filter_ids, success)

    async def _fetch_filter_names(self, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(SavedFilter.id, SavedFilter.name).where(SavedFilter.id.in_(ids))
            )
            return {row[0]: row[1] for row in result.all()}

    async def _dispatch_via_apprise(
        self, title: str, html_body: str, text_body: str
    ) -> bool:
        ap = apprise.Apprise()
        for url in self._urls:
            ap.add(url)

        def _notify_sync() -> bool:
            return bool(
                ap.notify(
                    title=title,
                    body=html_body,
                    body_format=apprise.NotifyFormat.HTML,
                )
            )

        try:
            return await asyncio.to_thread(_notify_sync)
        except Exception:
            logger.exception("Apprise dispatch failed")
            return False

    async def _log_dispatch(
        self,
        deals: list["SaleItem"],
        filter_ids: list[int],
        success: bool,
    ) -> None:
        row = NotificationLog(
            channel="apprise",
            filter_ids=filter_ids,
            deal_count=len(deals),
            status="success" if success else "failed",
            error=None if success else "Apprise dispatch returned no successes",
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(row)
        except Exception:
            logger.exception("Failed to write notification_log row")

    # --- Placeholder renderers (replaced by Jinja templates in PR-C) -----

    def _render_title(self, deals: list["SaleItem"]) -> str:
        count = len(deals)
        return f"Uniqlo Sale Alert — {count} deal{'s' if count != 1 else ''}"

    def _render_text(
        self, deals: list["SaleItem"], names_by_id: dict[int, str]
    ) -> str:
        lines = [f"{len(deals)} deal(s) matched your filters:", ""]
        for d in deals:
            tags = self._tag_string(d, names_by_id)
            lines.append(f"- {d.name} ({d.gender}) — {d.discount_percentage:.0f}% off{tags}")
        return "\n".join(lines)

    def _render_html(
        self, deals: list["SaleItem"], names_by_id: dict[int, str]
    ) -> str:
        parts = [
            "<html><body>",
            f"<p>{len(deals)} deal(s) matched your filters:</p>",
            "<ul>",
        ]
        for d in deals:
            tags = self._tag_string(d, names_by_id)
            parts.append(
                f"<li>{d.name} ({d.gender}) — {d.discount_percentage:.0f}% off{tags}</li>"
            )
        parts.append("</ul></body></html>")
        return "".join(parts)

    def _tag_string(
        self, deal: "SaleItem", names_by_id: dict[int, str]
    ) -> str:
        if deal.is_watched and not deal.matched_filter_ids:
            return " [Watched]"
        names = [names_by_id.get(i, f"#{i}") for i in deal.matched_filter_ids]
        return f" [matches: {', '.join(names)}]" if names else ""

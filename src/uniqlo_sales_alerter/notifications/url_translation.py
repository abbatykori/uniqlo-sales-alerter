"""Translate legacy ``channels.telegram`` / ``channels.email`` config into Apprise URLs.

PR-D's hard cutover routes everything through one
:class:`uniqlo_sales_alerter.notifications.apprise_notifier.AppriseNotifier`.
Existing installs whose ``config.yaml`` still uses the legacy
``channels.telegram`` and ``channels.email`` blocks (rather than the new
``notifications.apprise_urls`` list) get their URLs auto-translated at
startup, so no manual config migration is needed.

The legacy fields are still parsed by Pydantic so old YAML loads without
errors; they're simply no longer dispatched to as separate notifiers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import NotificationConfig

logger = logging.getLogger(__name__)


def _telegram_to_apprise_url(token: str, chat_id: str) -> str:
    """Build ``tgram://<bot_token>/<chat_id>``."""
    return f"tgram://{token}/{chat_id}"


def _email_to_apprise_url(
    *,
    smtp_user: str,
    smtp_password: str,
    smtp_host: str,
    smtp_port: int,
    use_tls: bool,
    from_address: str,
    to_addresses: list[str],
) -> str:
    """Build Apprise ``mailto://`` for one outbound mailer.

    Apprise's mailto syntax: ``mailto://user:password@host[:port]?from=&to=&secure=``.
    The ``secure`` query string controls TLS: ``yes`` enables STARTTLS / implicit
    TLS depending on the port, ``no`` sends plaintext.
    """
    auth = ""
    if smtp_user:
        auth = f"{quote(smtp_user, safe='')}:{quote(smtp_password, safe='')}@"
    port_seg = f":{smtp_port}" if smtp_port not in (25, 465, 587) else ""
    return (
        f"mailto://{auth}{smtp_host}{port_seg}/"
        f"?from={quote(from_address, safe='')}"
        f"&to={quote(','.join(to_addresses), safe='')}"
        f"&secure={'yes' if use_tls else 'no'}"
    )


def legacy_channels_to_apprise_urls(cfg: NotificationConfig) -> list[str]:
    """Return Apprise URLs derived from the legacy ``channels.*`` config.

    Disabled blocks (or blocks missing required fields) contribute nothing.
    Called once at :class:`NotificationDispatcher` init; the result is
    concatenated with ``cfg.apprise_urls`` to form the full URL set.
    """
    urls: list[str] = []

    tg = cfg.channels.telegram
    if tg.enabled and tg.bot_token and tg.chat_id:
        urls.append(_telegram_to_apprise_url(tg.bot_token, tg.chat_id))
        logger.debug("Translated legacy telegram block into Apprise URL")

    em = cfg.channels.email
    if em.enabled and em.smtp_host and em.from_address and em.to_addresses:
        urls.append(
            _email_to_apprise_url(
                smtp_user=em.smtp_user,
                smtp_password=em.smtp_password,
                smtp_host=em.smtp_host,
                smtp_port=em.smtp_port,
                use_tls=em.use_tls,
                from_address=em.from_address,
                to_addresses=em.to_addresses,
            )
        )
        logger.debug("Translated legacy email block into Apprise URL")

    return urls

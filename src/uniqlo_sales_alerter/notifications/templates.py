"""Jinja-based renderers for the Apprise notification body and title.

Three public functions:

- :func:`render_title` — short single-line title (e.g. for email Subject)
- :func:`render_html` — full HTML body shown by mail clients and Apprise targets
  that accept HTML (Telegram via HTML mode, Discord, Slack with HTML adapter,
  etc.). Surfaces matched-filter chips, watched badge, low-stock spans, and
  per-variant size links.
- :func:`render_text` — plaintext fallback for plain-only targets.

The templates re-use the channel-agnostic helpers in
:mod:`uniqlo_sales_alerter.notifications.base` (``format_price``,
``format_stock_suffix``, ``format_rating``, ``resolve_color_image``,
``unique_colors``, ``DealActions``), so notification behaviour stays
consistent with the legacy channels until PR-D retires them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

from uniqlo_sales_alerter.models.products import parse_variant_codes
from uniqlo_sales_alerter.notifications.action_urls import sign_action
from uniqlo_sales_alerter.notifications.base import (
    FormattedPrice,
    format_price,
    format_rating,
    format_stock_suffix,
    resolve_color_image,
    unique_colors,
)

if TYPE_CHECKING:
    from uniqlo_sales_alerter.models.products import SaleItem

_TEMPLATE_DIR = Path(__file__).parent / "jinja_templates"


def _autoescape_select(template_name: str | None) -> bool:
    """Autoescape templates whose name suggests HTML output.

    ``select_autoescape`` ships with only file-extension matching which
    doesn't see ``.j2``-suffixed names as HTML. We look for ``.html``
    anywhere in the name (``email.html.j2`` qualifies; ``email.txt.j2``
    does not).
    """
    if template_name is None:
        return False
    return ".html" in template_name


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=_autoescape_select,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["format_price"] = format_price
    env.globals["format_rating"] = format_rating
    env.globals["unique_colors"] = unique_colors
    return env


@dataclass(frozen=True, slots=True)
class SizeCell:
    """Per-size rendering data: link, label, stock suffix, low-stock flag."""

    label: str
    url: str
    image_url: str | None
    stock_text: str
    is_low_stock: bool


def _size_cells(
    deal: "SaleItem", *, low_stock_threshold: int
) -> list[SizeCell]:
    cells: list[SizeCell] = []
    for idx, size_label in enumerate(deal.available_sizes):
        variant = deal.variant_at(idx)
        stock_text, is_low = format_stock_suffix(
            variant.quantity, variant.status, low_stock_threshold
        )
        image_url = resolve_color_image(
            variant.url, deal.color_images, deal.image_url
        )
        cells.append(
            SizeCell(
                label=size_label,
                url=variant.url,
                image_url=image_url,
                stock_text=stock_text,
                is_low_stock=is_low,
            )
        )
    return cells


def _matched_names(
    deal: "SaleItem", names_by_id: dict[int, str]
) -> list[str]:
    return [names_by_id.get(fid, f"#{fid}") for fid in deal.matched_filter_ids]


def _signed_action_urls(
    deal: "SaleItem",
    server_url: str,
    secret: str,
    matched_filter_ids: list[int],
) -> dict:
    """Build all signed action URLs for one deal.

    Returns a dict with ``ignore_url``, ``watch_url_by_size``,
    ``unwatch_url_by_size``, and ``snooze_urls_by_filter`` (mapping
    filter_id → list[(label, url)] for 1d/7d/30d/forever). Empty when
    *server_url* or *secret* is unset (no actionable URLs possible).
    """
    if not server_url or not secret:
        return dict(
            ignore_url="",
            watch_url_by_size={},
            unwatch_url_by_size={},
            snooze_urls_by_filter={},
        )

    ignore_url = sign_action(
        secret=secret,
        base_url=server_url,
        action="ignore",
        path_arg=deal.product_id,
        payload={"name": deal.name},
    )

    watch_url_by_size: dict[str, str] = {}
    unwatch_url_by_size: dict[str, str] = {}
    for size_label, product_url in zip(deal.available_sizes, deal.product_urls):
        color, size_code = parse_variant_codes(product_url)
        if deal.is_watched:
            unwatch_url_by_size[size_label] = sign_action(
                secret=secret,
                base_url=server_url,
                action="unwatch",
                path_arg=deal.product_id,
                payload={
                    "name": deal.name,
                    "color": color,
                    "size": size_code,
                },
            )
        else:
            watch_url_by_size[size_label] = sign_action(
                secret=secret,
                base_url=server_url,
                action="watch",
                path_arg=deal.product_id,
                payload={"name": deal.name, "url": product_url},
            )

    snooze_urls_by_filter: dict[int, list[tuple[str, str]]] = {}
    for fid in matched_filter_ids:
        per_filter = []
        for label, duration in (
            ("1d", "1d"),
            ("7d", "7d"),
            ("30d", "30d"),
            ("forever", "forever"),
        ):
            url = sign_action(
                secret=secret,
                base_url=server_url,
                action="snooze",
                payload={"filter_id": str(fid), "duration": duration},
            )
            per_filter.append((label, url))
        snooze_urls_by_filter[fid] = per_filter

    return dict(
        ignore_url=ignore_url,
        watch_url_by_size=watch_url_by_size,
        unwatch_url_by_size=unwatch_url_by_size,
        snooze_urls_by_filter=snooze_urls_by_filter,
    )


def _build_view(
    deals: list["SaleItem"],
    names_by_id: dict[int, str],
    *,
    server_url: str,
    low_stock_threshold: int,
    secret: str,
) -> list[dict]:
    """Pre-compute per-deal view objects to keep the templates dumb."""
    view = []
    for deal in deals:
        price: FormattedPrice = format_price(deal)
        rating = format_rating(deal)
        cells = _size_cells(deal, low_stock_threshold=low_stock_threshold)
        actions = _signed_action_urls(
            deal, server_url, secret, deal.matched_filter_ids
        )
        view.append(
            dict(
                deal=deal,
                price=price,
                rating=rating,
                colors=unique_colors(deal),
                matched_filter_names=_matched_names(deal, names_by_id),
                size_cells=cells,
                **actions,
            )
        )
    return view


def render_title(deals: list["SaleItem"]) -> str:
    count = len(deals)
    template = _env().get_template("title.j2")
    return template.render(deal_count=count).strip()


def render_html(
    deals: list["SaleItem"],
    names_by_id: dict[int, str],
    *,
    server_url: str = "",
    low_stock_threshold: int = 0,
    secret: str = "",
) -> str:
    view = _build_view(
        deals,
        names_by_id,
        server_url=server_url,
        low_stock_threshold=low_stock_threshold,
        secret=secret,
    )
    template = _env().get_template("email.html.j2")
    return template.render(
        deals=view, server_url=server_url, names_by_id=names_by_id,
    )


def render_text(
    deals: list["SaleItem"],
    names_by_id: dict[int, str],
    *,
    server_url: str = "",
    low_stock_threshold: int = 0,
    secret: str = "",
) -> str:
    view = _build_view(
        deals,
        names_by_id,
        server_url=server_url,
        low_stock_threshold=low_stock_threshold,
        secret=secret,
    )
    template = _env().get_template("email.txt.j2")
    return template.render(deals=view, server_url=server_url)

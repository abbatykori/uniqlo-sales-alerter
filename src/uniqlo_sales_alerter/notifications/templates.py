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

from uniqlo_sales_alerter.notifications.base import (
    DealActions,
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


def _build_view(
    deals: list["SaleItem"],
    names_by_id: dict[int, str],
    *,
    server_url: str,
    low_stock_threshold: int,
) -> list[dict]:
    """Pre-compute per-deal view objects to keep the templates dumb."""
    view = []
    for deal in deals:
        actions = DealActions(deal, server_url)
        price: FormattedPrice = format_price(deal)
        rating = format_rating(deal)
        cells = _size_cells(deal, low_stock_threshold=low_stock_threshold)
        watch_url_by_size = {label: url for label, url in actions.watch_urls}
        unwatch_url_by_size = {label: url for label, url in actions.unwatch_urls}
        view.append(
            dict(
                deal=deal,
                price=price,
                rating=rating,
                colors=unique_colors(deal),
                matched_filter_names=_matched_names(deal, names_by_id),
                size_cells=cells,
                ignore_url=actions.ignore_url,
                watch_url_by_size=watch_url_by_size,
                unwatch_url_by_size=unwatch_url_by_size,
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
) -> str:
    view = _build_view(
        deals,
        names_by_id,
        server_url=server_url,
        low_stock_threshold=low_stock_threshold,
    )
    template = _env().get_template("email.html.j2")
    return template.render(deals=view, server_url=server_url)


def render_text(
    deals: list["SaleItem"],
    names_by_id: dict[int, str],
    *,
    server_url: str = "",
    low_stock_threshold: int = 0,
) -> str:
    view = _build_view(
        deals,
        names_by_id,
        server_url=server_url,
        low_stock_threshold=low_stock_threshold,
    )
    template = _env().get_template("email.txt.j2")
    return template.render(deals=view, server_url=server_url)

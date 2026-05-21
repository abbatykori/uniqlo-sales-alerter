"""Jinja template rendering: matched-filter chips, watched badge, low-stock styling."""

from __future__ import annotations

from tests.conftest import sample_deal
from uniqlo_sales_alerter.notifications.templates import (
    render_html,
    render_text,
    render_title,
)


def test_title_with_single_deal_uses_singular() -> None:
    title = render_title([sample_deal()])
    assert "1 deal" in title
    assert "deals" not in title


def test_title_with_multiple_deals_uses_plural() -> None:
    title = render_title([sample_deal(product_id="A"), sample_deal(product_id="B")])
    assert "2 deals" in title


def test_html_includes_deal_name_and_price() -> None:
    deal = sample_deal(
        product_id="E001",
        name="Soft Tee",
        original_price=39.90,
        sale_price=19.90,
        discount_percentage=50.1,
    )
    html = render_html([deal], {})
    assert "Soft Tee" in html
    assert "19.90" in html
    assert "-50%" in html
    # Strikethrough applies to original price
    assert "line-through" in html
    assert "39.90" in html


def test_html_renders_matched_filter_chips() -> None:
    deal = sample_deal(product_id="E001", matched_filter_ids=[7, 12])
    html = render_html([deal], {7: "Me tops", 12: "Spouse"})
    assert "Me tops" in html
    assert "Spouse" in html
    # Chips render as rounded badges
    assert "border-radius:9999px" in html


def test_html_falls_back_to_id_when_name_missing() -> None:
    deal = sample_deal(product_id="E001", matched_filter_ids=[42])
    html = render_html([deal], {})  # empty lookup table
    assert "#42" in html


def test_html_watched_badge_when_no_matched_filters() -> None:
    deal = sample_deal(product_id="E001", is_watched=True, matched_filter_ids=[])
    html = render_html([deal], {})
    assert "Watched" in html


def test_html_unknown_discount_renders_sale_badge() -> None:
    deal = sample_deal(
        product_id="E001",
        has_known_discount=False,
        discount_percentage=0.0,
        original_price=29.90,
        sale_price=29.90,
    )
    html = render_html([deal], {})
    # Sale badge present, no strikethrough
    assert "Sale" in html
    assert "line-through" not in html


def test_html_low_stock_red_styling_appears() -> None:
    deal = sample_deal(
        product_id="E001",
        available_sizes=["M"],
        product_urls=[
            "https://www.uniqlo.com/de/de/products/E001/00?colorDisplayCode=00&sizeDisplayCode=001"
        ],
        stock_quantities=[2],
        stock_statuses=["LOW_STOCK"],
    )
    html = render_html([deal], {}, low_stock_threshold=5)
    # Low-stock pill is the warning red
    assert "#A14040" in html


def test_html_includes_action_links_when_server_url_set() -> None:
    deal = sample_deal(product_id="E001", available_sizes=["M"])
    html = render_html([deal], {}, server_url="http://localhost:8000")
    assert "/actions/ignore/E001" in html
    assert "Watch M" in html


def test_html_hides_action_links_without_server_url() -> None:
    deal = sample_deal(product_id="E001")
    html = render_html([deal], {})
    assert "/actions/ignore/" not in html
    assert "Set server_url" in html


def test_html_unwatch_links_appear_for_watched_items() -> None:
    deal = sample_deal(product_id="E001", is_watched=True, available_sizes=["M"])
    html = render_html([deal], {}, server_url="http://localhost:8000")
    assert "Unwatch M" in html
    # Should NOT also show a "Watch M" link when already watched
    assert "Watch M" not in html.replace("Unwatch M", "")


def test_text_body_includes_filter_names_and_sizes() -> None:
    deal = sample_deal(product_id="E001", matched_filter_ids=[1], available_sizes=["M", "L"])
    text = render_text([deal], {1: "Me tops"})
    assert "Me tops" in text
    assert "Sizes:" in text
    assert "- M" in text
    assert "- L" in text


def test_text_body_marks_low_stock() -> None:
    deal = sample_deal(
        product_id="E001",
        available_sizes=["M"],
        product_urls=[
            "https://www.uniqlo.com/de/de/products/E001/00?colorDisplayCode=00&sizeDisplayCode=001"
        ],
        stock_quantities=[1],
        stock_statuses=["LOW_STOCK"],
    )
    text = render_text([deal], {}, low_stock_threshold=5)
    assert "low stock" in text.lower()


def test_text_body_indicates_watched() -> None:
    deal = sample_deal(product_id="E001", is_watched=True)
    text = render_text([deal], {})
    assert "[WATCHED]" in text


def test_html_safe_against_injection_in_deal_name() -> None:
    """Autoescape should neutralise HTML in product names."""
    deal = sample_deal(name="<script>alert(1)</script>")
    html = render_html([deal], {})
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "&lt;script" in html

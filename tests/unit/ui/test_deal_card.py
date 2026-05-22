"""Deal-card partial — click target + price layout."""

from __future__ import annotations

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.ui.routes import templates


def _render_deal_card(deal: SaleItem) -> str:
    template = templates.get_template("_deal_card.html")
    return template.render({"deal": deal})


def _sample_deal(**overrides) -> SaleItem:
    base = {
        "product_id": "123456",
        "name": "Test product",
        "original_price": 39.90,
        "sale_price": 19.90,
        "currency_symbol": "€",
        "discount_percentage": 50.0,
        "gender": "men",
        "available_sizes": ["M", "L"],
        "image_url": "https://example.com/img.jpg",
        "product_urls": [
            "https://www.uniqlo.com/eu/en/products/E123456-000/00?colorCode=00&sizeCode=02",
            "https://www.uniqlo.com/eu/en/products/E123456-000/00?colorCode=00&sizeCode=03",
        ],
    }
    base.update(overrides)
    return SaleItem(**base)


def test_card_links_image_to_first_variant_in_new_tab() -> None:
    html = _render_deal_card(_sample_deal())
    # Jinja autoescaping turns & into &amp; — match the escaped href.
    expected = (
        '<a href="https://www.uniqlo.com/eu/en/products/E123456-000/'
        '00?colorCode=00&amp;sizeCode=02" target="_blank" rel="noopener"'
    )
    assert expected in html


def test_card_has_view_on_uniqlo_cta() -> None:
    html = _render_deal_card(_sample_deal())
    assert "View on Uniqlo" in html


def test_card_size_pills_open_in_new_tab() -> None:
    html = _render_deal_card(_sample_deal())
    # Each size pill must carry target=_blank rel=noopener so it opens externally.
    assert html.count('target="_blank"') >= 3  # image + 2 size pills + cta


def test_price_block_stacks_strikethrough_above_sale() -> None:
    html = _render_deal_card(_sample_deal())
    # Strikethrough original appears in its own <div> *before* the sale price block.
    strike_idx = html.find("line-through")
    sale_idx = html.find("text-status-error")
    assert strike_idx != -1
    assert sale_idx != -1
    assert strike_idx < sale_idx, "original price must precede sale price"


def test_no_discount_renders_sale_badge_only() -> None:
    deal = _sample_deal(
        original_price=19.90,
        sale_price=19.90,
        discount_percentage=0.0,
        has_known_discount=False,
    )
    html = _render_deal_card(deal)
    assert "line-through" not in html
    assert "Sale" in html


def test_card_renders_without_image_or_urls() -> None:
    deal = _sample_deal(image_url=None, product_urls=[], available_sizes=[])
    html = _render_deal_card(deal)
    assert "No image" in html
    # No CTA when there's no URL to link to.
    assert "View on Uniqlo" not in html

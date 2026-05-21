"""Invoice paste parser — handoff §5 fixture + 5 synthetic variants."""

from __future__ import annotations

from uniqlo_sales_alerter.parsers.invoice_paste import parse_invoice

# ---- handoff §5 NL fixture (verbatim) -----------------------------------

HANDOFF_NL_INVOICE = """\
47492809120000, Track Joggers
BLACK, 5-6 Years (120cm)
Price: 1 x 9,90€
Subtotal: 9,90€
(VAT Rate 21%): 1,72€
46932256006000, AIRism Cotton Oversized Mock Neck T-Shirt (Half Sleeve)
OLIVE, XL
Price: 1 x 12,90€
Subtotal: 12,90€
(VAT Rate 21%): 2,24€
46518662007000, Crew Neck T-Shirt
BLUE, XXL
Price: 2 x 7,90€
Subtotal: 15,80€
(VAT Rate 21%): 2,74€
46518757006000, DRY Colour Crew Neck T-Shirt
OLIVE, XL
Price: 1 x 5,90€
Subtotal: 5,90€
(VAT Rate 21%): 1,02€
46549431006000, 100% Supima Cotton T-Shirt
BEIGE, XL
Price: 1 x 12,90€
Subtotal: 12,90€
(VAT Rate 21%): 2,24€
"""


def test_handoff_nl_invoice_clothing_sizes():
    """XL appears 3 times, XXL once → dedup to {XL, XXL}."""
    result = parse_invoice(HANDOFF_NL_INVOICE)
    assert sorted(result.clothing) == ["XL", "XXL"]


def test_handoff_nl_invoice_kids_sizes():
    """5-6 Years (120cm) → canonical 120cm."""
    result = parse_invoice(HANDOFF_NL_INVOICE)
    assert result.kids == ["120cm"]


def test_handoff_nl_invoice_product_ids():
    result = parse_invoice(HANDOFF_NL_INVOICE)
    assert result.product_ids == [
        "47492809120000",
        "46932256006000",
        "46518662007000",
        "46518757006000",
        "46549431006000",
    ]


def test_handoff_nl_invoice_colours():
    result = parse_invoice(HANDOFF_NL_INVOICE)
    assert sorted(result.colors) == ["BEIGE", "BLACK", "BLUE", "OLIVE"]


def test_handoff_nl_invoice_no_pants_or_shoes():
    result = parse_invoice(HANDOFF_NL_INVOICE)
    assert result.pants == []
    assert result.shoes == []
    assert result.one_size is False


# ---- synthetic fixtures --------------------------------------------------

_PANTS_INVOICE = """\
46999999000000, Stretch Slim-Fit Jeans
BLUE, 32inch
Price: 1 x 49,90€
"""


def test_pants_invoice():
    result = parse_invoice(_PANTS_INVOICE)
    assert result.pants == ["32inch"]
    assert result.colors == ["BLUE"]


_SHOES_INVOICE = """\
46888888000000, Knit Slip-On Trainers
BEIGE, 42.5
Price: 1 x 39,90€
"""


def test_shoes_invoice_half_size():
    result = parse_invoice(_SHOES_INVOICE)
    assert result.shoes == ["42.5"]


_ONE_SIZE_INVOICE = """\
46777777000000, Heattech Knit Scarf
BLACK, One Size
Price: 1 x 14,90€
"""


def test_one_size_flag():
    result = parse_invoice(_ONE_SIZE_INVOICE)
    assert result.one_size is True
    assert result.clothing == []
    assert result.pants == []


_MULTI_QTY_INVOICE = """\
46666666000000, AIRism Boxer Briefs
BLACK, M
Price: 4 x 6,90€
Subtotal: 27,60€
46666666000000, AIRism Boxer Briefs
BLACK, M
Price: 2 x 6,90€
Subtotal: 13,80€
"""


def test_multi_quantity_and_repeat_dedup():
    """Multiple lines for the same product/size should dedup."""
    result = parse_invoice(_MULTI_QTY_INVOICE)
    assert result.clothing == ["M"]
    # Product ID listed once even though it appears twice
    assert result.product_ids == ["46666666000000"]
    # Colour listed once
    assert result.colors == ["BLACK"]


_MIXED_ENCODING_INVOICE = (
    "47492809120000, Track Joggers\n"
    "BLACK​, 5-6 Years (120cm)\n"  # zero-width space after colour
    "Price: 1 x 9,90€\n"
    "﻿46932256006000, AIRism Cotton Oversized Mock Neck T-Shirt\n"  # BOM
    "OLIVE, XL\n"
    "Price: 1 x 12,90€\n"
)


def test_mixed_encoding_invisible_chars_stripped():
    """BOMs and zero-width spaces from PDF extraction must not break parsing."""
    result = parse_invoice(_MIXED_ENCODING_INVOICE)
    assert result.kids == ["120cm"]
    assert result.clothing == ["XL"]
    assert sorted(result.colors) == ["BLACK", "OLIVE"]


_NON_EURO_INVOICE = """\
44555555000000, Soft Tee
WHITE, L
Price: 1 x $24.90
Subtotal: $24.90
"""


def test_currency_agnostic():
    """The parser only looks at colour/size lines; currency on price lines is ignored."""
    result = parse_invoice(_NON_EURO_INVOICE)
    assert result.clothing == ["L"]


# ---- edge cases ----------------------------------------------------------


def test_empty_input_returns_empty_result():
    result = parse_invoice("")
    assert result.clothing == []
    assert result.product_ids == []
    assert result.colors == []
    assert result.one_size is False


def test_random_unrelated_text_yields_no_sizes():
    result = parse_invoice("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
    assert result.clothing == []
    assert result.product_ids == []


def test_unparseable_size_line_recorded():
    """A colour/size line with an unrecognised size token shows up in unparsed."""
    bad = (
        "46333333000000, Mystery Thing\n"
        "RED, HUGE\n"
        "Price: 1 x 9,90€\n"
    )
    result = parse_invoice(bad)
    assert result.colors == ["RED"]
    assert result.clothing == []
    assert any("RED" in line and "HUGE" in line for line in result.unparsed_lines)

"""Size-string categorisation."""

from __future__ import annotations

import pytest

from uniqlo_sales_alerter.parsers.size import parse_size


@pytest.mark.parametrize("raw", ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL"])
def test_clothing_sizes(raw):
    parsed = parse_size(raw)
    assert parsed is not None
    assert parsed.category == "clothing"
    assert parsed.canonical == raw


def test_clothing_lowercase_is_normalised():
    parsed = parse_size("xl")
    assert parsed.category == "clothing"
    assert parsed.canonical == "XL"


@pytest.mark.parametrize("raw,canonical", [
    ("32inch", "32inch"),
    ("28inch", "28inch"),
    ("40inch", "40inch"),
    ("22inch", "22inch"),
])
def test_pants_inches(raw, canonical):
    parsed = parse_size(raw)
    assert parsed.category == "pants"
    assert parsed.canonical == canonical


def test_pants_out_of_range_rejected():
    assert parse_size("80inch") is None
    assert parse_size("19inch") is None


@pytest.mark.parametrize("raw,canonical", [
    ("42", "42"),
    ("42.5", "42.5"),
    ("37", "37"),
    ("43", "43"),
])
def test_shoe_sizes(raw, canonical):
    parsed = parse_size(raw)
    assert parsed.category == "shoes"
    assert parsed.canonical == canonical


def test_shoe_out_of_range_rejected():
    assert parse_size("30") is None
    assert parse_size("50") is None


@pytest.mark.parametrize("raw,canonical", [
    ("120cm", "120cm"),
    ("80cm", "80cm"),
    ("150 cm", "150cm"),
])
def test_kids_cm(raw, canonical):
    parsed = parse_size(raw)
    assert parsed.category == "kids"
    assert parsed.canonical == canonical


@pytest.mark.parametrize("raw,canonical", [
    ("5-6 Years (120cm)", "120cm"),
    ("3-4 Years (100cm)", "100cm"),
    ("1 Year (80cm)", "80cm"),
])
def test_kids_years_normalised_to_cm(raw, canonical):
    parsed = parse_size(raw)
    assert parsed.category == "kids"
    assert parsed.canonical == canonical


def test_one_size_not_categorised():
    assert parse_size("One Size") is None


def test_empty_string_returns_none():
    assert parse_size("") is None
    assert parse_size("   ") is None


def test_unknown_garbage_returns_none():
    assert parse_size("HUGE") is None
    assert parse_size("Petite") is None
    assert parse_size("12inch") is None  # below pants range

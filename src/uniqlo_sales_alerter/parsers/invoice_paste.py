"""Extract size suggestions from a pasted Uniqlo invoice.

The Uniqlo NL invoice (and similar) ships product blocks of three lines:

    47492809120000, Track Joggers
    BLACK, 5-6 Years (120cm)
    Price: 1 x 9,90€

We capture the *second* line per block — ``<COLOR>, <SIZE>`` — and
categorise each size via :mod:`parsers.size`. Multi-line invoices
deduplicate sizes across blocks; the suggestion UI presents the canonical
form (``120cm`` rather than ``5-6 Years``).

The handoff §5 NL fixture is the primary test target; synthetic
variants cover pants / shoes / kids / one-size / multi-quantity /
non-Euro currency / mixed encoding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from uniqlo_sales_alerter.parsers.size import ParsedSize, parse_size

_PRODUCT_HEADER_RE = re.compile(r"^\s*(\d{10,16})\s*,\s*(.+?)\s*$")
_COLOUR_SIZE_RE = re.compile(r"^\s*([A-Z][A-Z /]+?)\s*,\s*(.+?)\s*$")
# Some invoices have invisible Unicode (zero-width spaces, BOM); strip them up front.
_INVISIBLE_RE = re.compile(r"[​‌‍﻿]")


@dataclass(frozen=True, slots=True)
class ParsedInvoice:
    """Result of :func:`parse_invoice` — deduplicated, canonicalised."""

    clothing: list[str] = field(default_factory=list)
    pants: list[str] = field(default_factory=list)
    shoes: list[str] = field(default_factory=list)
    kids: list[str] = field(default_factory=list)
    one_size: bool = False  # any line with size="One Size" triggers this
    product_ids: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    unparsed_lines: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return _INVISIBLE_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def parse_invoice(text: str) -> ParsedInvoice:
    """Walk *text* line-by-line, extract sizes + product IDs + colours."""
    lines = _clean(text).split("\n")

    clothing: list[str] = []
    pants: list[str] = []
    shoes: list[str] = []
    kids: list[str] = []
    one_size = False
    product_ids: list[str] = []
    colors: list[str] = []
    unparsed: list[str] = []

    seen_product: dict[str, bool] = {}  # id → already-added
    seen_clothing: set[str] = set()
    seen_pants: set[str] = set()
    seen_shoes: set[str] = set()
    seen_kids: set[str] = set()
    seen_colors: set[str] = set()

    prev_was_product = False
    for raw in lines:
        s = raw.strip()
        if not s:
            prev_was_product = False
            continue

        header = _PRODUCT_HEADER_RE.match(s)
        if header:
            pid = header.group(1)
            if pid not in seen_product:
                seen_product[pid] = True
                product_ids.append(pid)
            prev_was_product = True
            continue

        if prev_was_product:
            color_size = _COLOUR_SIZE_RE.match(s)
            prev_was_product = False
            if color_size:
                color = color_size.group(1).strip().upper()
                size_token = color_size.group(2).strip()
                if color and color not in seen_colors:
                    seen_colors.add(color)
                    colors.append(color)
                if size_token.lower() == "one size":
                    one_size = True
                    continue
                parsed: ParsedSize | None = parse_size(size_token)
                if parsed is None:
                    unparsed.append(s)
                    continue
                target_seen, target_list = {
                    "clothing": (seen_clothing, clothing),
                    "pants": (seen_pants, pants),
                    "shoes": (seen_shoes, shoes),
                    "kids": (seen_kids, kids),
                }[parsed.category]
                if parsed.canonical not in target_seen:
                    target_seen.add(parsed.canonical)
                    target_list.append(parsed.canonical)
                continue

        # Line wasn't a product header or a colour/size — just continuation
        # text (Price:, Subtotal:, VAT). Ignore.

    return ParsedInvoice(
        clothing=clothing,
        pants=pants,
        shoes=shoes,
        kids=kids,
        one_size=one_size,
        product_ids=product_ids,
        colors=colors,
        unparsed_lines=unparsed,
    )

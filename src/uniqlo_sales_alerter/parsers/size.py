"""Size-string categorisation.

Maps a raw size token (``"XL"``, ``"32inch"``, ``"42.5"``,
``"120cm"``, ``"5-6 Years (120cm)"``) to one of four buckets:

- ``clothing`` — XXS / XS / S / M / L / XL / XXL / 3XL
- ``pants`` — N inch (where N is 22-40, even)
- ``shoes`` — numeric 37-43 with optional half-step (``.5``)
- ``kids`` — ``<N>cm`` (60-180) or ``<years> Years (<N>cm)``

Returns ``None`` for unrecognised tokens (a one-size accessory, etc. —
they're handled separately as ``one_size_match``). The kids parser
prefers the canonical ``<N>cm`` form: ``"5-6 Years (120cm)" → "120cm"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Category = Literal["clothing", "pants", "shoes", "kids"]

_CLOTHING_RE = re.compile(r"^(XXS|XS|S|M|L|XL|XXL|3XL)$", re.IGNORECASE)
_PANTS_RE = re.compile(r"^(\d{2})\s*inch$", re.IGNORECASE)
_SHOES_RE = re.compile(r"^(\d{2})(\.5)?$")
_KIDS_CM_ONLY_RE = re.compile(r"^(\d{2,3})\s*cm$", re.IGNORECASE)
_KIDS_YEARS_RE = re.compile(
    r"^\d+\s*[-/]?\s*\d*\s*Years?\s*\(?\s*(\d{2,3})\s*cm\s*\)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedSize:
    """One categorised size with the normalised canonical form."""

    category: Category
    canonical: str


def parse_size(raw: str) -> ParsedSize | None:
    """Return a :class:`ParsedSize` or ``None`` if the token is unrecognised."""
    token = raw.strip()
    if not token:
        return None

    m = _CLOTHING_RE.match(token)
    if m:
        return ParsedSize("clothing", m.group(1).upper())

    m = _PANTS_RE.match(token)
    if m:
        inches = int(m.group(1))
        if 22 <= inches <= 40:
            return ParsedSize("pants", f"{inches}inch")

    m = _KIDS_YEARS_RE.match(token)
    if m:
        return ParsedSize("kids", f"{int(m.group(1))}cm")

    m = _KIDS_CM_ONLY_RE.match(token)
    if m:
        cm = int(m.group(1))
        if 60 <= cm <= 180:
            return ParsedSize("kids", f"{cm}cm")

    m = _SHOES_RE.match(token)
    if m:
        whole = int(m.group(1))
        half = m.group(2) or ""
        if 37 <= whole <= 43:
            return ParsedSize("shoes", f"{whole}{half}")

    return None

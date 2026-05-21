"""REST endpoints for content parsers (currently only invoice paste)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from uniqlo_sales_alerter.parsers.invoice_paste import parse_invoice

router = APIRouter(prefix="/api/v1/parsers", tags=["parsers"])


class InvoicePasteIn(BaseModel):
    """Request body for ``POST /api/v1/parsers/invoice``."""

    text: str = Field(min_length=1)


class InvoicePasteOut(BaseModel):
    """Categorised size suggestions plus debug surfaces."""

    clothing: list[str]
    pants: list[str]
    shoes: list[str]
    kids: list[str]
    one_size: bool
    product_ids: list[str]
    colors: list[str]
    unparsed_lines: list[str]


@router.post("/invoice", response_model=InvoicePasteOut)
def parse_invoice_endpoint(body: InvoicePasteIn) -> InvoicePasteOut:
    """Parse a pasted invoice and return categorised size suggestions."""
    result = parse_invoice(body.text)
    return InvoicePasteOut(
        clothing=result.clothing,
        pants=result.pants,
        shoes=result.shoes,
        kids=result.kids,
        one_size=result.one_size,
        product_ids=result.product_ids,
        colors=result.colors,
        unparsed_lines=result.unparsed_lines,
    )

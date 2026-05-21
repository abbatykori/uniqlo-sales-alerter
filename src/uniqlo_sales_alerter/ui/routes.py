"""HTMX-driven UI for the new saved filters.

Hidden route — intentionally not linked from the legacy ``/settings`` page or
any navigation. The legacy single-filter editor on ``/settings`` remains the
authoritative editor while the matcher still consumes ``config.yaml::filters``.
Step 8 swaps the matcher onto the SQLite-backed ``saved_filters`` table and
exposes this UI in the nav at that point.

Templates live under :data:`TEMPLATES_DIR`. Each form submission returns an
HTML partial sized for HTMX swap, not JSON.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from uniqlo_sales_alerter.api.schemas import SavedFilterCreate, SavedFilterUpdate
from uniqlo_sales_alerter.db.engine import get_session
from uniqlo_sales_alerter.services.saved_filters import (
    DuplicateFilterName,
    FilterNotFound,
    create_filter,
    delete_filter,
    get_filter,
    list_filters,
    resume_filter,
    snooze_filter,
    update_filter,
)

TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui", tags=["ui"])


def _parse_comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_payload_from_form(
    *,
    name: str,
    gender: str,
    min_discount: float,
    sizes_clothing: str,
    sizes_pants: str,
    sizes_shoes: str,
    one_size_match: bool,
    availability_mode: str,
    ignored_keywords: str,
    enabled: bool,
    snooze_until: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "gender": _parse_comma_list(gender),
        "min_discount": min_discount,
        "sizes_clothing": _parse_comma_list(sizes_clothing),
        "sizes_pants": _parse_comma_list(sizes_pants),
        "sizes_shoes": _parse_comma_list(sizes_shoes),
        "one_size_match": one_size_match,
        "availability_mode": availability_mode,
        "ignored_keywords": _parse_comma_list(ignored_keywords),
        "enabled": enabled,
    }
    if snooze_until:
        payload["snooze_until"] = datetime.fromisoformat(snooze_until)
    return payload


@router.get("/filters", response_class=HTMLResponse)
async def list_view(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    rows = await list_filters(session)
    return templates.TemplateResponse(
        request, "filters/list.html", {"filters": rows}
    )


@router.get("/filters/new", response_class=HTMLResponse)
async def new_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "filters/edit.html", {"filter": None, "errors": None}
    )


@router.get("/filters/{filter_id}/edit", response_class=HTMLResponse)
async def edit_form(
    request: Request, filter_id: int, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    try:
        row = await get_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return templates.TemplateResponse(
        request, "filters/edit.html", {"filter": row, "errors": None}
    )


@router.post("/filters", response_class=HTMLResponse)
async def create_view(
    request: Request,
    name: str = Form(...),
    gender: str = Form(""),
    min_discount: float = Form(0.0),
    sizes_clothing: str = Form(""),
    sizes_pants: str = Form(""),
    sizes_shoes: str = Form(""),
    one_size_match: bool = Form(False),
    availability_mode: str = Form("both"),
    ignored_keywords: str = Form(""),
    enabled: bool = Form(True),
    snooze_until: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    payload_dict = _build_payload_from_form(
        name=name,
        gender=gender,
        min_discount=min_discount,
        sizes_clothing=sizes_clothing,
        sizes_pants=sizes_pants,
        sizes_shoes=sizes_shoes,
        one_size_match=one_size_match,
        availability_mode=availability_mode,
        ignored_keywords=ignored_keywords,
        enabled=enabled,
        snooze_until=snooze_until,
    )
    try:
        data = SavedFilterCreate.model_validate(payload_dict)
        row = await create_filter(session, data)
    except (ValueError, DuplicateFilterName) as exc:
        return HTMLResponse(
            templates.get_template("filters/edit.html").render(
                {
                    "request": request,
                    "filter": None,
                    "errors": str(exc),
                }
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return templates.TemplateResponse(
        request,
        "filters/_row.html",
        {"f": row},
        status_code=status.HTTP_201_CREATED,
    )


@router.put("/filters/{filter_id}", response_class=HTMLResponse)
async def update_view(
    request: Request,
    filter_id: int,
    name: str = Form(...),
    gender: str = Form(""),
    min_discount: float = Form(0.0),
    sizes_clothing: str = Form(""),
    sizes_pants: str = Form(""),
    sizes_shoes: str = Form(""),
    one_size_match: bool = Form(False),
    availability_mode: str = Form("both"),
    ignored_keywords: str = Form(""),
    enabled: bool = Form(True),
    snooze_until: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    payload_dict = _build_payload_from_form(
        name=name,
        gender=gender,
        min_discount=min_discount,
        sizes_clothing=sizes_clothing,
        sizes_pants=sizes_pants,
        sizes_shoes=sizes_shoes,
        one_size_match=one_size_match,
        availability_mode=availability_mode,
        ignored_keywords=ignored_keywords,
        enabled=enabled,
        snooze_until=snooze_until,
    )
    try:
        data = SavedFilterUpdate.model_validate(payload_dict)
        row = await update_filter(session, filter_id, data)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except (ValueError, DuplicateFilterName) as exc:
        return HTMLResponse(
            templates.get_template("filters/edit.html").render(
                {
                    "request": request,
                    "filter": {"id": filter_id},
                    "errors": str(exc),
                }
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return templates.TemplateResponse(request, "filters/_row.html", {"f": row})


@router.delete("/filters/{filter_id}")
async def delete_view(
    filter_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    try:
        await delete_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    # HTMX swaps the row out by returning empty content.
    return HTMLResponse("", status_code=status.HTTP_200_OK)


@router.get("/filters/{filter_id}/snooze", response_class=HTMLResponse)
async def snooze_popover(
    request: Request, filter_id: int
) -> HTMLResponse:
    """Return the snooze-duration popover partial."""
    return templates.TemplateResponse(
        request, "filters/_snooze_popover.html", {"filter_id": filter_id}
    )


@router.post("/filters/{filter_id}/snooze", response_class=HTMLResponse)
async def snooze_view(
    request: Request,
    filter_id: int,
    duration: str = Form("7d"),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    try:
        row = await snooze_filter(session, filter_id, duration)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    return templates.TemplateResponse(request, "filters/_row.html", {"f": row})


@router.post("/filters/{filter_id}/resume", response_class=HTMLResponse)
async def resume_view(
    request: Request,
    filter_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    try:
        row = await resume_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return templates.TemplateResponse(request, "filters/_row.html", {"f": row})

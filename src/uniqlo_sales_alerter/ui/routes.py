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
from uniqlo_sales_alerter.services.heatmap import aggregate as aggregate_heatmap
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

router = APIRouter(prefix="", tags=["ui"])


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


_DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


async def _status_pill_context(request: Request) -> dict:
    """Build the data feeding the global status pill in base.html."""
    from datetime import datetime, timezone

    from sqlalchemy import func, or_, select

    from uniqlo_sales_alerter.db.engine import async_session_factory
    from uniqlo_sales_alerter.db.models import SavedFilter

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session_factory() as session:
        active_stmt = (
            select(func.count(SavedFilter.id))
            .where(SavedFilter.enabled == 1)
            .where(
                or_(
                    SavedFilter.snooze_until.is_(None),
                    SavedFilter.snooze_until <= now,
                )
            )
        )
        snoozed_stmt = (
            select(func.count(SavedFilter.id))
            .where(SavedFilter.enabled == 1)
            .where(SavedFilter.snooze_until.is_not(None))
            .where(SavedFilter.snooze_until > now)
        )
        active = (await session.execute(active_stmt)).scalar_one()
        snoozed = (await session.execute(snoozed_stmt)).scalar_one()

    last_check_age = None
    app_state = getattr(request.app.state, "app_state", None)
    if app_state and app_state.last_check_at is not None:
        last_at = app_state.last_check_at
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        last_check_age = int((datetime.now(timezone.utc) - last_at).total_seconds())

    return {
        "active_filters": int(active),
        "snoozed_filters": int(snoozed),
        "last_check_age_seconds": last_check_age,
    }


@router.get("/status-pill", response_class=HTMLResponse)
async def status_pill(request: Request) -> HTMLResponse:
    """HTMX-polled status pill fragment for base.html."""
    ctx = await _status_pill_context(request)
    return templates.TemplateResponse(request, "_status_pill.html", ctx)


@router.get("/", response_class=HTMLResponse)
async def deals_view(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Default landing — deals grouped by saved filter."""
    app_state = getattr(request.app.state, "app_state", None)
    last_result = (
        app_state.sale_checker.last_result if app_state is not None else None
    )
    filters = await list_filters(session)
    names_by_id = {f.id: f.name for f in filters}

    deals_by_filter: dict[int, list] = {}
    untagged_watched: list = []
    if last_result is not None:
        for deal in last_result.matching_deals:
            if not deal.matched_filter_ids and deal.is_watched:
                untagged_watched.append(deal)
            for fid in deal.matched_filter_ids:
                deals_by_filter.setdefault(fid, []).append(deal)

    return templates.TemplateResponse(
        request, "deals.html",
        {
            "filters": filters,
            "names_by_id": names_by_id,
            "deals_by_filter": deals_by_filter,
            "watched_only": untagged_watched,
            "last_check_at": (
                app_state.last_check_at if app_state is not None else None
            ),
        },
    )


@router.get("/inbox", response_class=HTMLResponse)
async def inbox_view(request: Request) -> HTMLResponse:
    """Notification history from the ``notification_log`` table."""
    from sqlalchemy import select

    from uniqlo_sales_alerter.db.engine import async_session_factory
    from uniqlo_sales_alerter.db.models import NotificationLog

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(NotificationLog).order_by(NotificationLog.sent_at.desc()).limit(50)
            )
        ).scalars().all()
    return templates.TemplateResponse(
        request, "inbox.html", {"rows": rows},
    )


@router.get("/help", response_class=HTMLResponse)
async def help_index(request: Request) -> HTMLResponse:
    """Diataxis index stub linking the four content categories."""
    return templates.TemplateResponse(request, "help/index.html", {})


_HELP_SECTIONS = {"tutorials", "how-to", "reference", "explanation"}


@router.get("/help/{section}", response_class=HTMLResponse)
async def help_section(request: Request, section: str) -> HTMLResponse:
    """Render one of the four Diataxis stub pages."""
    if section not in _HELP_SECTIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        request, f"help/{section}.html", {"section": section}
    )


@router.get("/filters/paste", response_class=HTMLResponse)
async def paste_invoice_form(request: Request) -> HTMLResponse:
    """Render the invoice-paste textarea page."""
    return templates.TemplateResponse(
        request, "filters/paste_invoice.html", {"result": None}
    )


@router.post("/filters/paste", response_class=HTMLResponse)
async def paste_invoice_parse(
    request: Request,
    text: str = Form(""),
) -> HTMLResponse:
    """Parse pasted text and return the chip-suggestion HTMX partial."""
    from uniqlo_sales_alerter.parsers.invoice_paste import parse_invoice

    result = parse_invoice(text) if text.strip() else None
    return templates.TemplateResponse(
        request,
        "filters/_paste_suggestions.html",
        {"result": result},
    )


@router.get("/insights", response_class=HTMLResponse)
async def insights_view(
    request: Request,
    lookback: int = 90,
) -> HTMLResponse:
    """Deal heatmap — 7 days × 24 hours grid of deep-discount counts."""
    view = await aggregate_heatmap(lookback_days=lookback)
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "view": view,
            "day_labels": _DAY_LABELS,
        },
    )

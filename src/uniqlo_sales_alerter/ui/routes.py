"""HTMX-driven UI: saved filters, deals/inbox/insights, settings.

Each route returns either a full page (extends ``base.html``) or an HTML
partial sized for an HTMX swap. JSON is reserved for ``/api/v1``.
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
    gender: list[str],
    min_discount: float,
    sizes_clothing: list[str],
    sizes_pants: list[str],
    sizes_shoes: list[str],
    one_size_match: bool,
    availability_mode: str,
    ignored_keywords: str,
    snooze_until: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "gender": gender,
        "min_discount": min_discount,
        "sizes_clothing": sizes_clothing,
        "sizes_pants": sizes_pants,
        "sizes_shoes": sizes_shoes,
        "one_size_match": one_size_match,
        "availability_mode": availability_mode,
        "ignored_keywords": _parse_comma_list(ignored_keywords),
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
    gender: list[str] = Form(default_factory=list),
    min_discount: float = Form(0.0),
    sizes_clothing: list[str] = Form(default_factory=list),
    sizes_pants: list[str] = Form(default_factory=list),
    sizes_shoes: list[str] = Form(default_factory=list),
    one_size_match: bool = Form(False),
    availability_mode: str = Form("both"),
    ignored_keywords: str = Form(""),
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
    gender: list[str] = Form(default_factory=list),
    min_discount: float = Form(0.0),
    sizes_clothing: list[str] = Form(default_factory=list),
    sizes_pants: list[str] = Form(default_factory=list),
    sizes_shoes: list[str] = Form(default_factory=list),
    one_size_match: bool = Form(False),
    availability_mode: str = Form("both"),
    ignored_keywords: str = Form(""),
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
async def snooze_modal(
    request: Request, filter_id: int
) -> HTMLResponse:
    """Return the snooze-duration modal partial swapped into ``#modal-content``."""
    return templates.TemplateResponse(
        request, "filters/_snooze_modal.html", {"filter_id": filter_id}
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


# ---------------------------------------------------------------------------
# Settings page — Apprise URLs, schedule, country, watched, ignored.
# ---------------------------------------------------------------------------


def _app_state(request: Request):
    """Return the FastAPI app's mutable state holder."""
    return request.app.state.app_state


async def _persist_config(request: Request) -> None:
    """Save the in-memory config to disk and reload the scheduler."""
    from uniqlo_sales_alerter.config import save_config
    from uniqlo_sales_alerter.main import reload_config

    save_config(_app_state(request).config)
    await reload_config(request.app)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Tailwind-based settings page — replaces the v2.0 inline-HTML editor."""
    state = _app_state(request)
    config = state.config
    return templates.TemplateResponse(
        request,
        "settings/index.html",
        {
            "config": config,
            "apprise_urls": list(config.notifications.apprise_urls),
            "watched": list(config.filters.watched_variants),
            "ignored_products": list(config.filters.ignored_products),
            "ignored_keywords": list(config.filters.ignored_keywords),
        },
    )


# ---- Apprise URLs ---------------------------------------------------------


@router.post("/settings/apprise", response_class=HTMLResponse)
async def settings_apprise_add(
    request: Request,
    url: str = Form(...),
) -> HTMLResponse:
    """Append a new Apprise URL to the notification list."""
    config = _app_state(request).config
    cleaned = url.strip()
    if cleaned and cleaned not in config.notifications.apprise_urls:
        config.notifications.apprise_urls.append(cleaned)
        await _persist_config(request)
    return templates.TemplateResponse(
        request,
        "settings/_apprise_list.html",
        {"apprise_urls": list(_app_state(request).config.notifications.apprise_urls)},
    )


@router.delete("/settings/apprise/{index}", response_class=HTMLResponse)
async def settings_apprise_remove(request: Request, index: int) -> HTMLResponse:
    """Remove an Apprise URL by list index."""
    config = _app_state(request).config
    if 0 <= index < len(config.notifications.apprise_urls):
        config.notifications.apprise_urls.pop(index)
        await _persist_config(request)
    return templates.TemplateResponse(
        request,
        "settings/_apprise_list.html",
        {"apprise_urls": list(_app_state(request).config.notifications.apprise_urls)},
    )


@router.post("/settings/apprise/{index}/test", response_class=HTMLResponse)
async def settings_apprise_test(request: Request, index: int) -> HTMLResponse:
    """Dispatch a synthetic test deal through one Apprise URL only."""
    from uniqlo_sales_alerter.models.products import SaleItem
    from uniqlo_sales_alerter.notifications.apprise_notifier import AppriseNotifier

    config = _app_state(request).config
    if not (0 <= index < len(config.notifications.apprise_urls)):
        raise HTTPException(status_code=404, detail="Unknown Apprise URL")

    target_url = config.notifications.apprise_urls[index]
    test_deal = SaleItem(
        product_id="0",
        name="[TEST] Uniqlo Alerter test notification",
        original_price=0.0,
        sale_price=0.0,
        currency_symbol="€",
        discount_percentage=0.0,
        gender="unisex",
        available_sizes=["M"],
        product_urls=[""],
        matched_filter_ids=[-1],
    )

    notifier = AppriseNotifier(urls=[target_url])
    try:
        await notifier.send([test_deal])
        message = "Test notification dispatched."
        css_class = "text-status-success"
    except Exception as exc:
        message = f"Test failed: {exc}"
        css_class = "text-status-error"
    return HTMLResponse(
        f'<p class="text-sm {css_class}">{message}</p>'
    )


# ---- Schedule / quiet hours ----------------------------------------------


@router.post("/settings/schedule", response_class=HTMLResponse)
async def settings_schedule_update(
    request: Request,
    check_interval_minutes: int = Form(...),
    scheduled_checks: str = Form(""),
    quiet_enabled: bool = Form(False),
    quiet_start: str = Form("01:00"),
    quiet_end: str = Form("08:00"),
) -> HTMLResponse:
    from pydantic import ValidationError

    from uniqlo_sales_alerter.config import QuietHoursConfig

    config = _app_state(request).config
    try:
        config.uniqlo.check_interval_minutes = max(0, int(check_interval_minutes))
        config.uniqlo.scheduled_checks = [
            t.strip() for t in scheduled_checks.split(",") if t.strip()
        ]
        config.quiet_hours = QuietHoursConfig(
            enabled=quiet_enabled,
            start=quiet_start,
            end=quiet_end,
        )
        await _persist_config(request)
    except (ValueError, ValidationError) as exc:
        return HTMLResponse(
            f'<span class="text-status-error">Save failed: {exc}</span>'
        )
    return HTMLResponse(
        '<span class="text-status-success">Saved.</span>'
    )


# ---- Country / language --------------------------------------------------


@router.post("/settings/country", response_class=HTMLResponse)
async def settings_country_update(
    request: Request,
    store_country: str = Form(...),
    ui_language: str = Form(""),
) -> HTMLResponse:
    config = _app_state(request).config
    config.store_country = store_country.strip().lower()
    config.ui_language = ui_language.strip().lower() or None
    try:
        await _persist_config(request)
    except Exception as exc:
        return HTMLResponse(
            f'<span class="text-status-error">Save failed: {exc}</span>'
        )
    return HTMLResponse(
        '<span class="text-status-success">Saved. Restart for full effect.</span>'
    )


# ---- Watched variants ----------------------------------------------------


@router.post("/settings/watched", response_class=HTMLResponse)
async def settings_watched_add(
    request: Request,
    url: str = Form(...),
) -> HTMLResponse:
    from pydantic import ValidationError

    from uniqlo_sales_alerter.config import WatchedVariant

    config = _app_state(request).config
    try:
        variant = WatchedVariant(url=url.strip())
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not variant.id:
        raise HTTPException(status_code=400, detail="Could not parse product ID from URL")

    config.filters.watched_variants.append(variant)
    await _persist_config(request)
    return templates.TemplateResponse(
        request,
        "settings/_watched_list.html",
        {"watched": list(_app_state(request).config.filters.watched_variants)},
    )


@router.delete("/settings/watched/{index}", response_class=HTMLResponse)
async def settings_watched_remove(request: Request, index: int) -> HTMLResponse:
    config = _app_state(request).config
    if 0 <= index < len(config.filters.watched_variants):
        config.filters.watched_variants.pop(index)
        await _persist_config(request)
    return templates.TemplateResponse(
        request,
        "settings/_watched_list.html",
        {"watched": list(_app_state(request).config.filters.watched_variants)},
    )


# ---- Ignored products & keywords -----------------------------------------


def _render_ignored(request: Request) -> HTMLResponse:
    config = _app_state(request).config
    return templates.TemplateResponse(
        request,
        "settings/_ignored_lists.html",
        {
            "ignored_products": list(config.filters.ignored_products),
            "ignored_keywords": list(config.filters.ignored_keywords),
        },
    )


@router.delete("/settings/ignored/products/{index}", response_class=HTMLResponse)
async def settings_ignored_product_remove(
    request: Request, index: int
) -> HTMLResponse:
    config = _app_state(request).config
    if 0 <= index < len(config.filters.ignored_products):
        config.filters.ignored_products.pop(index)
        await _persist_config(request)
    return _render_ignored(request)


@router.post("/settings/ignored/keywords", response_class=HTMLResponse)
async def settings_ignored_keyword_add(
    request: Request, keyword: str = Form(...),
) -> HTMLResponse:
    config = _app_state(request).config
    cleaned = keyword.strip().lower()
    if cleaned and cleaned not in [k.lower() for k in config.filters.ignored_keywords]:
        config.filters.ignored_keywords.append(cleaned)
        await _persist_config(request)
    return _render_ignored(request)


@router.delete("/settings/ignored/keywords/{index}", response_class=HTMLResponse)
async def settings_ignored_keyword_remove(
    request: Request, index: int
) -> HTMLResponse:
    config = _app_state(request).config
    if 0 <= index < len(config.filters.ignored_keywords):
        config.filters.ignored_keywords.pop(index)
        await _persist_config(request)
    return _render_ignored(request)

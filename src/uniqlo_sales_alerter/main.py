"""Application entry-point — FastAPI app, lifespan, and scheduler wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from time import monotonic
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from uniqlo_sales_alerter.api.health import router as health_router
from uniqlo_sales_alerter.api.parsers import router as parsers_router
from uniqlo_sales_alerter.api.routes import actions_router, router
from uniqlo_sales_alerter.api.saved_filters import router as saved_filters_router
from uniqlo_sales_alerter.clients.uniqlo import UniqloClient
from uniqlo_sales_alerter.config import AppConfig, load_config, save_config
from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import CheckHistory, DealObservation
from uniqlo_sales_alerter.db.schema import ensure_schema
from uniqlo_sales_alerter.models.products import SaleCheckResult
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.secret import load_or_create_secret
from uniqlo_sales_alerter.services.bridge_migration import ensure_bridge_migration
from uniqlo_sales_alerter.services.enrichment import enrich_config
from uniqlo_sales_alerter.services.sale_checker import SaleChecker
from uniqlo_sales_alerter.services.upstream_migration import ensure_upstream_migration
from uniqlo_sales_alerter.ui.routes import router as ui_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    config: AppConfig
    sale_checker: SaleChecker
    dispatcher: NotificationDispatcher
    scheduler: AsyncIOScheduler = field(default_factory=AsyncIOScheduler)
    last_check_at: datetime | None = None
    secret: str = ""


def _is_deep(result: SaleCheckResult, threshold: int) -> int:
    """Count deals matching the configured deep-discount threshold."""
    return sum(
        1
        for d in result.matching_deals
        if d.has_known_discount and d.discount_percentage >= threshold
    )


async def _write_check_history(
    *,
    duration_ms: int,
    result: SaleCheckResult | None,
    error: str | None,
    deep_threshold: int,
) -> None:
    """Persist one row to ``check_history`` per :func:`run_sale_check` invocation."""
    row = CheckHistory(
        duration_ms=duration_ms,
        deals_scanned=result.total_products_scanned if result else 0,
        deals_matched=len(result.matching_deals) if result else 0,
        deep_discounts=_is_deep(result, deep_threshold) if result else 0,
        error=error,
    )
    async with async_session_factory() as session:
        async with session.begin():
            session.add(row)


async def _write_deal_observations(
    result: SaleCheckResult, deep_threshold: int
) -> None:
    """Insert one ``deal_observations`` row per matched deal.

    The heatmap aggregation in :mod:`services.heatmap` reads this table.
    Failures here are non-fatal — the sale check has already succeeded.
    """
    if not result.matching_deals:
        return
    rows = [
        DealObservation(
            product_id=d.product_id,
            discount_pct=d.discount_percentage if d.has_known_discount else None,
            is_deep=int(d.has_known_discount and d.discount_percentage >= deep_threshold),
        )
        for d in result.matching_deals
    ]
    try:
        async with async_session_factory() as session:
            async with session.begin():
                session.add_all(rows)
    except Exception:
        logger.exception("Failed to write deal_observations rows")


async def _load_last_check_at() -> datetime | None:
    """Return the most recent ``check_history.ran_at`` (timezone-aware UTC)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(CheckHistory.ran_at).order_by(CheckHistory.ran_at.desc()).limit(1)
        )
        row = result.scalar()
    if row is None:
        return None
    # SQLite stores naive timestamps; treat them as UTC.
    return row.replace(tzinfo=timezone.utc) if row.tzinfo is None else row


def _in_quiet_hours(config: AppConfig) -> bool:
    """Return ``True`` if the current local time falls within the configured quiet window."""
    quiet = config.quiet_hours
    if not quiet.enabled:
        return False
    start_h, start_m = map(int, quiet.start.split(":"))
    end_h, end_m = map(int, quiet.end.split(":"))
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    now = datetime.now().time()
    if start <= end:
        return start <= now < end
    # Wraps midnight (e.g. 23:00 → 06:00)
    return now >= start or now < end


async def run_sale_check(app_state: AppState) -> SaleCheckResult:
    """Execute a sale check, persist a ``check_history`` row, and dispatch notifications."""
    started = monotonic()
    result: SaleCheckResult | None = None
    error_text: str | None = None
    deep_threshold = app_state.config.deep_discount_threshold
    try:
        result = await app_state.sale_checker.check()
        app_state.last_check_at = datetime.now(timezone.utc)
        logger.info(
            "Sale check complete — %d matching deals (%d new)",
            len(result.matching_deals),
            len(result.new_deals),
        )

        notify_on = app_state.config.notifications.notify_on
        deals_to_notify = (
            result.matching_deals if notify_on == "every_check" else result.new_deals
        )
        if deals_to_notify:
            await app_state.dispatcher.dispatch(deals_to_notify)

        return result

    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        logger.exception("Sale check failed")
        raise

    finally:
        if result is not None:
            await _write_deal_observations(result, deep_threshold)
        duration_ms = int((monotonic() - started) * 1000)
        try:
            await _write_check_history(
                duration_ms=duration_ms,
                result=result,
                error=error_text,
                deep_threshold=deep_threshold,
            )
        except Exception:
            logger.exception("Failed to write check_history row")


def _add_check_job(app_state: AppState) -> None:
    """Register periodic and/or fixed-time sale checks with the scheduler."""

    async def _interval_job() -> None:
        if _in_quiet_hours(app_state.config):
            logger.debug("Quiet hours active (%s – %s) — skipping periodic check",
                         app_state.config.quiet_hours.start,
                         app_state.config.quiet_hours.end)
            return
        interval = app_state.config.uniqlo.check_interval_minutes
        if (
            app_state.last_check_at
            and datetime.now(timezone.utc) - app_state.last_check_at
            < timedelta(minutes=interval * 0.8)
        ):
            logger.debug(
                "Skipping periodic check — a scheduled check ran recently",
            )
            return
        await run_sale_check(app_state)

    async def _scheduled_job() -> None:
        await run_sale_check(app_state)

    interval = app_state.config.uniqlo.check_interval_minutes
    if interval > 0:
        app_state.scheduler.add_job(
            _interval_job, "interval", minutes=interval,
            id="sale_check_interval",
        )
        logger.info("Scheduled periodic checks every %d minute(s)", interval)
    else:
        logger.info("Periodic checks disabled (check_interval_minutes=0)")

    for check_time in app_state.config.uniqlo.scheduled_checks:
        hour, minute = check_time.split(":")
        app_state.scheduler.add_job(
            _scheduled_job, "cron",
            hour=int(hour), minute=int(minute),
            id=f"sale_check_{check_time}",
        )
        logger.info("Scheduled fixed check at %s", check_time)

    async def _prune_seen_variants() -> None:
        try:
            deleted = await app_state.sale_checker._state.prune_older_than(365)
            logger.info("Pruned %d seen_variants rows older than 365 days", deleted)
        except Exception:
            logger.exception("Daily seen_variants prune failed")

    app_state.scheduler.add_job(
        _prune_seen_variants, "cron",
        hour=3, minute=15,
        id="prune_seen_variants",
    )
    logger.info("Daily seen_variants prune scheduled at 03:15 UTC")



async def _try_enrich(config: AppConfig, client: UniqloClient) -> None:
    """Enrich watched/ignored metadata; save config if anything changed."""
    try:
        if await enrich_config(config, client):
            save_config(config)
    except Exception:
        logger.warning("Watched-variant enrichment failed — will retry later")


async def reload_config(app: FastAPI) -> AppConfig:
    """Reload configuration from YAML (without re-applying env overrides)."""
    current: AppState = app.state.app_state
    current.scheduler.remove_all_jobs()
    await current.sale_checker.close()

    config = load_config(apply_env_overrides=False)
    await _run_bridge_migration(config)
    await _run_upstream_migration(config)
    checker = SaleChecker(config)
    await _try_enrich(config, checker.http_client)

    dispatcher = NotificationDispatcher(config, secret=current.secret)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=current.scheduler,
        last_check_at=current.last_check_at,
        secret=current.secret,
    )

    _add_check_job(app.state.app_state)
    logger.info("Config reloaded")
    return config


async def _run_bridge_migration(config: AppConfig) -> None:
    """Seed the legacy single filter into ``saved_filters`` once per install."""
    async with async_session_factory() as session:
        async with session.begin():
            await ensure_bridge_migration(session, config)


async def _run_upstream_migration(config: AppConfig) -> None:
    """Import upstream watched/ignored/seen state once per install (best-effort)."""
    try:
        async with async_session_factory() as session:
            async with session.begin():
                await ensure_upstream_migration(session, config)
    except Exception:
        logger.exception("Upstream migration failed — leaving source files in place")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ensure_schema()

    config = load_config()
    save_config(config)

    await _run_bridge_migration(config)

    secret = load_or_create_secret()
    last_check_at = await _load_last_check_at()

    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config, secret=secret)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        last_check_at=last_check_at,
        secret=secret,
    )

    await _try_enrich(config, checker.http_client)

    app_state: AppState = app.state.app_state
    _add_check_job(app_state)
    app_state.scheduler.start()

    if config.notifications.check_on_startup:
        try:
            await run_sale_check(app_state)
        except Exception:
            logger.exception("Initial sale check failed — will retry on schedule")
    else:
        logger.info("Startup check disabled (check_on_startup=false)")

    logger.info("Settings UI: http://localhost:%d/settings", config.port)

    yield

    app_state = app.state.app_state
    app_state.scheduler.shutdown(wait=False)
    await app_state.sale_checker.close()
    logger.info("Scheduler stopped")


try:
    _APP_VERSION = version("uniqlo-sales-alerter")
except PackageNotFoundError:  # running from a checkout without an installed dist
    _APP_VERSION = "0.0.0+unknown"


app = FastAPI(
    title="Uniqlo Sales Alerter",
    description="Monitors Uniqlo sales and surfaces deals matching your criteria.",
    version=_APP_VERSION,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(router)
app.include_router(actions_router)
app.include_router(saved_filters_router)
app.include_router(parsers_router)
app.include_router(ui_router)

# Mount /static for the design-token CSS and any vendored assets (Phosphor SVGs).
from pathlib import Path as _Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = _Path(__file__).parent / "ui" / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/ui/{path:path}", include_in_schema=False)
async def legacy_ui_redirect(path: str) -> RedirectResponse:
    """Permanent redirect from the v2.0 ``/ui/*`` paths to the new root-mounted UI."""
    target = f"/{path}" if path else "/"
    return RedirectResponse(url=target, status_code=308)

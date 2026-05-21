"""Healthcheck endpoint.

Reports liveness signals that the container orchestrator and load balancer can
poll. The set of checks grows as the foundation phase progresses:

- Step 2 (this file): scheduler-running check; DB and last-check slots stub to ``None``.
- Step 3: ``db_writeable`` is populated via :func:`db.engine.health_probe`.
- Step 9 (future): ``last_check_age_seconds`` is populated from scheduler heartbeat.

Any non-``None`` field that is ``False`` flips the response to HTTP 503.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from uniqlo_sales_alerter.db.engine import health_probe
from uniqlo_sales_alerter.i18n import _

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Response body for the ``/health`` endpoint."""

    status: Literal["ok", "degraded"]
    db_writeable: bool | None
    scheduler_running: bool | None
    last_check_age_seconds: int | None
    last_check_fresh: bool | None
    message: str


@router.get("/health", response_model=HealthStatus)
async def health(request: Request) -> JSONResponse:
    """Return the current health status."""
    app_state = getattr(request.app.state, "app_state", None)
    scheduler_running: bool | None
    if app_state is None or app_state.scheduler is None:
        scheduler_running = None
    else:
        scheduler_running = bool(app_state.scheduler.running)

    db_writeable: bool | None = await health_probe()

    last_check_age_seconds: int | None = None
    last_check_fresh: bool | None = None
    if app_state is not None and app_state.last_check_at is not None:
        last_at = app_state.last_check_at
        # SQLite stores naive datetimes; treat them as UTC for the age calc.
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        age = int((datetime.now(timezone.utc) - last_at).total_seconds())
        last_check_age_seconds = max(age, 0)
        interval_minutes = app_state.config.uniqlo.check_interval_minutes
        if interval_minutes > 0:
            last_check_fresh = last_check_age_seconds <= 2 * interval_minutes * 60

    checks = (db_writeable, scheduler_running, last_check_fresh)
    degraded = any(value is False for value in checks)

    body = HealthStatus(
        status="degraded" if degraded else "ok",
        db_writeable=db_writeable,
        scheduler_running=scheduler_running,
        last_check_age_seconds=last_check_age_seconds,
        last_check_fresh=last_check_fresh,
        message=_("Degraded") if degraded else _("Healthy"),
    )
    return JSONResponse(
        status_code=503 if degraded else 200,
        content=body.model_dump(),
    )

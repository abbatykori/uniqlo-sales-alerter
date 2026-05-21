"""Daily seen_variants prune cron is registered with the scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.main import AppState, _add_check_job
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


def _app_state(*, interval: int = 30, scheduled: list[str] | None = None) -> AppState:
    config = AppConfig.model_validate({
        "uniqlo": {
            "country": "nl/nl",
            "check_interval_minutes": interval,
            "scheduled_checks": scheduled or [],
        },
    })
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    scheduler = MagicMock(running=False)
    state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=scheduler,
    )
    return state


def test_prune_cron_registered_with_03_15_utc():
    state = _app_state()
    _add_check_job(state)
    add_job_calls = state.scheduler.add_job.call_args_list
    prune_call = next(
        c for c in add_job_calls if c.kwargs.get("id") == "prune_seen_variants"
    )
    assert prune_call.args[1] == "cron"
    assert prune_call.kwargs["hour"] == 3
    assert prune_call.kwargs["minute"] == 15


def test_prune_cron_registered_even_when_periodic_disabled():
    """Prune still runs daily even if check_interval_minutes=0."""
    state = _app_state(interval=0)
    _add_check_job(state)
    ids = [c.kwargs.get("id") for c in state.scheduler.add_job.call_args_list]
    assert "prune_seen_variants" in ids
    # No periodic job in this case
    assert "sale_check_interval" not in ids


def test_prune_cron_coexists_with_scheduled_checks():
    state = _app_state(interval=0, scheduled=["09:00", "21:00"])
    _add_check_job(state)
    ids = [c.kwargs.get("id") for c in state.scheduler.add_job.call_args_list]
    assert "prune_seen_variants" in ids
    assert "sale_check_09:00" in ids
    assert "sale_check_21:00" in ids

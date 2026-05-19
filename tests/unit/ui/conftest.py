"""Test fixtures shared by HTMX UI tests — same shape as the REST suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker


@pytest.fixture()
def client():
    from unittest.mock import MagicMock

    from uniqlo_sales_alerter.main import AppState, app

    config = AppConfig()
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=MagicMock(running=True),
    )
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_saved_filters():
    import asyncio

    from uniqlo_sales_alerter.db.engine import engine

    async def _truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM saved_filters"))

    asyncio.run(_truncate())
    yield

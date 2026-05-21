"""Deal-heatmap aggregation.

Reads ``deal_observations`` and produces a 7×24 grid of deep-discount
counts grouped by day-of-week (0=Sunday) × hour-of-day. The UI renders
each cell with opacity proportional to ``count / max_count`` clamped to
``[0.05, 1.0]`` so even zero cells stay visually legible.

The 14-day "insufficient data" threshold prevents an empty grid from
suggesting "no deals ever happen on Tuesdays" before enough observations
accrue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from uniqlo_sales_alerter.db.engine import async_session_factory
from uniqlo_sales_alerter.db.models import DealObservation

INSUFFICIENT_DATA_DAYS = 14
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_DEEP_THRESHOLD = 50


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    """One cell in the 7×24 grid."""

    day_of_week: int  # 0=Sunday … 6=Saturday (matches SQLite strftime('%w'))
    hour_of_day: int  # 0..23
    count: int
    opacity: float


@dataclass(frozen=True, slots=True)
class HeatmapView:
    """Full grid + sufficient-data flag for the template."""

    cells: tuple[HeatmapCell, ...]
    max_count: int
    distinct_days: int
    sufficient: bool
    lookback_days: int


def _empty_grid_cells() -> list[list[int]]:
    return [[0 for _ in range(24)] for _ in range(7)]


async def aggregate(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    only_deep: bool = True,
) -> HeatmapView:
    """Return the 7×24 grid for the rolling lookback window.

    ``only_deep=True`` counts only rows where ``is_deep=1``; set False to
    count every matched deal observation (useful for sanity-checking
    before deep-discount data accumulates).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    async with async_session_factory() as session:
        # Per-cell counts
        stmt = (
            select(
                func.strftime("%w", DealObservation.observed_at).label("dow"),
                func.strftime("%H", DealObservation.observed_at).label("hod"),
                func.count().label("cnt"),
            )
            .where(DealObservation.observed_at >= cutoff)
            .group_by("dow", "hod")
        )
        if only_deep:
            stmt = stmt.where(DealObservation.is_deep == 1)
        rows = (await session.execute(stmt)).all()

        # Distinct-day count for sufficient-data threshold (counts ALL
        # observations regardless of is_deep, so the heatmap unlocks even
        # without deep discounts).
        distinct_stmt = select(
            func.count(func.distinct(func.date(DealObservation.observed_at)))
        )
        distinct_days = int(
            (await session.execute(distinct_stmt)).scalar_one()
        )

    grid = _empty_grid_cells()
    for row in rows:
        dow, hod, cnt = int(row.dow), int(row.hod), int(row.cnt)
        if 0 <= dow < 7 and 0 <= hod < 24:
            grid[dow][hod] = cnt

    max_count = max((c for row in grid for c in row), default=0)
    cells: list[HeatmapCell] = []
    for dow in range(7):
        for hod in range(24):
            count = grid[dow][hod]
            opacity = 0.05
            if max_count > 0 and count > 0:
                opacity = max(0.05, min(1.0, count / max_count))
            cells.append(
                HeatmapCell(
                    day_of_week=dow,
                    hour_of_day=hod,
                    count=count,
                    opacity=opacity,
                )
            )

    return HeatmapView(
        cells=tuple(cells),
        max_count=max_count,
        distinct_days=distinct_days,
        sufficient=distinct_days >= INSUFFICIENT_DATA_DAYS,
        lookback_days=lookback_days,
    )

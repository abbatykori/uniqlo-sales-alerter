"""Service layer for the ``saved_filters`` table.

Wraps the ORM in async functions returning Pydantic models so the REST
handlers stay declarative. The matcher does NOT consume these rows in the
foundation phase — that happens in step 8 when the legacy single-filter
config is retired.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uniqlo_sales_alerter.api.schemas import (
    SavedFilterCreate,
    SavedFilterRead,
    SavedFilterUpdate,
)
from uniqlo_sales_alerter.db.models import SavedFilter


class DuplicateFilterName(ValueError):
    """Raised when a create/update would violate the unique-name constraint."""


class FilterNotFound(LookupError):
    """Raised when a filter ID does not exist."""


def _to_read(row: SavedFilter) -> SavedFilterRead:
    return SavedFilterRead.model_validate(row, from_attributes=True)


async def list_filters(session: AsyncSession) -> list[SavedFilterRead]:
    """Return every saved filter ordered by ``id``."""
    result = await session.execute(select(SavedFilter).order_by(SavedFilter.id))
    return [_to_read(row) for row in result.scalars()]


async def get_filter(session: AsyncSession, filter_id: int) -> SavedFilterRead:
    """Fetch a single filter by ID."""
    row = await session.get(SavedFilter, filter_id)
    if row is None:
        raise FilterNotFound(filter_id)
    return _to_read(row)


async def create_filter(
    session: AsyncSession, data: SavedFilterCreate
) -> SavedFilterRead:
    """Insert a new filter; raises :class:`DuplicateFilterName` on name collision."""
    row = SavedFilter(
        name=data.name,
        gender=data.gender,
        min_discount=data.min_discount,
        sizes_clothing=data.sizes_clothing,
        sizes_pants=data.sizes_pants,
        sizes_shoes=data.sizes_shoes,
        one_size_match=int(data.one_size_match),
        availability_mode=data.availability_mode,
        ignored_keywords=data.ignored_keywords,
        enabled=int(data.enabled),
        snooze_until=data.snooze_until,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateFilterName(data.name) from exc
    await session.refresh(row)
    return _to_read(row)


async def update_filter(
    session: AsyncSession, filter_id: int, data: SavedFilterUpdate
) -> SavedFilterRead:
    """Replace a filter's mutable fields. Raises :class:`FilterNotFound` if missing."""
    row = await session.get(SavedFilter, filter_id)
    if row is None:
        raise FilterNotFound(filter_id)
    row.name = data.name
    row.gender = data.gender
    row.min_discount = data.min_discount
    row.sizes_clothing = data.sizes_clothing
    row.sizes_pants = data.sizes_pants
    row.sizes_shoes = data.sizes_shoes
    row.one_size_match = int(data.one_size_match)
    row.availability_mode = data.availability_mode
    row.ignored_keywords = data.ignored_keywords
    row.enabled = int(data.enabled)
    row.snooze_until = data.snooze_until
    row.updated_at = datetime.now(timezone.utc)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateFilterName(data.name) from exc
    return _to_read(row)


async def delete_filter(session: AsyncSession, filter_id: int) -> None:
    """Delete a filter by ID. Raises :class:`FilterNotFound` if missing."""
    row = await session.get(SavedFilter, filter_id)
    if row is None:
        raise FilterNotFound(filter_id)
    await session.delete(row)


async def duplicate_filter(
    session: AsyncSession, filter_id: int
) -> SavedFilterRead:
    """Clone a filter into a new row with the suffix `` (copy)`` appended to the name."""
    source = await session.get(SavedFilter, filter_id)
    if source is None:
        raise FilterNotFound(filter_id)
    copy_name = f"{source.name} (copy)"
    payload = SavedFilterCreate(
        name=copy_name,
        gender=list(source.gender),
        min_discount=source.min_discount,
        sizes_clothing=list(source.sizes_clothing),
        sizes_pants=list(source.sizes_pants),
        sizes_shoes=list(source.sizes_shoes),
        one_size_match=bool(source.one_size_match),
        availability_mode=source.availability_mode,
        ignored_keywords=list(source.ignored_keywords),
        enabled=bool(source.enabled),
        snooze_until=source.snooze_until,
    )
    return await create_filter(session, payload)

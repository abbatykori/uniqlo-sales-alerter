"""REST endpoints for the new ``saved_filters`` table.

Lives at ``/api/v1/filters``. The legacy single global filter under
``config.yaml::filters`` is untouched — both shapes coexist for the
foundation phase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from uniqlo_sales_alerter.api.schemas import (
    SavedFilterCreate,
    SavedFilterRead,
    SavedFilterUpdate,
)
from uniqlo_sales_alerter.db.engine import get_session
from uniqlo_sales_alerter.services.saved_filters import (
    DuplicateFilterName,
    FilterNotFound,
    create_filter,
    delete_filter,
    duplicate_filter,
    get_filter,
    list_filters,
    update_filter,
)

router = APIRouter(prefix="/api/v1/filters", tags=["saved-filters"])


@router.get("", response_model=list[SavedFilterRead])
async def list_endpoint(
    session: AsyncSession = Depends(get_session),
) -> list[SavedFilterRead]:
    return await list_filters(session)


@router.post("", response_model=SavedFilterRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    payload: SavedFilterCreate,
    session: AsyncSession = Depends(get_session),
) -> SavedFilterRead:
    try:
        return await create_filter(session, payload)
    except DuplicateFilterName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"filter name already exists: {exc.args[0]}",
        ) from exc


@router.get("/{filter_id}", response_model=SavedFilterRead)
async def get_endpoint(
    filter_id: int,
    session: AsyncSession = Depends(get_session),
) -> SavedFilterRead:
    try:
        return await get_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc


@router.put("/{filter_id}", response_model=SavedFilterRead)
async def update_endpoint(
    filter_id: int,
    payload: SavedFilterUpdate,
    session: AsyncSession = Depends(get_session),
) -> SavedFilterRead:
    try:
        return await update_filter(session, filter_id, payload)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DuplicateFilterName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"filter name already exists: {exc.args[0]}",
        ) from exc


@router.delete("/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    filter_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await delete_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc


@router.post(
    "/{filter_id}/duplicate",
    response_model=SavedFilterRead,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_endpoint(
    filter_id: int,
    session: AsyncSession = Depends(get_session),
) -> SavedFilterRead:
    try:
        return await duplicate_filter(session, filter_id)
    except FilterNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except DuplicateFilterName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"filter name already exists: {exc.args[0]}",
        ) from exc

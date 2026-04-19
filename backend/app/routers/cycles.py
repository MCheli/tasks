"""Cycle endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.cycle import (
    CycleDetail,
    CycleListResponse,
    TransitionRequest,
    TransitionResponse,
)
from app.services import cycle_service

router = APIRouter()

CategoryParam = Query(..., pattern="^(personal|professional)$")


@router.get("/current", response_model=CycleDetail)
async def get_current(
    category: str = CategoryParam,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleDetail:
    cycle = await cycle_service.get_or_create_current_cycle(db, user, category)
    return await cycle_service.cycle_detail(db, user, cycle)


@router.get("", response_model=CycleListResponse)
async def list_cycles(
    category: str = CategoryParam,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleListResponse:
    return await cycle_service.list_cycles(db, user, category, limit=limit, offset=offset)


@router.get("/{cycle_id}", response_model=CycleDetail)
async def get_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CycleDetail:
    cycle = await cycle_service.get_cycle(db, user, cycle_id)
    return await cycle_service.cycle_detail(db, user, cycle)


@router.post(
    "/{cycle_id}/transition",
    response_model=TransitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transition(
    cycle_id: UUID,
    payload: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransitionResponse:
    return await cycle_service.transition_cycle(db, user, cycle_id, payload.actions)

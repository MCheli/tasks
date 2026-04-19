"""Task endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskCreateResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskReorderRequest,
    TaskUpdate,
    TaskUpdateResponse,
)
from app.services import task_service

router = APIRouter()


@router.post("", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskCreateResponse:
    task = await task_service.create_task(db, user, payload)
    return TaskCreateResponse(task=task)


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskDetailResponse:
    return await task_service.get_task_with_lineage(db, user, task_id)


@router.patch("/{task_id}", response_model=TaskUpdateResponse)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskUpdateResponse:
    task = await task_service.update_task(db, user, task_id, payload)
    return TaskUpdateResponse(task=task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await task_service.soft_delete_lineage(db, user, task_id)


@router.post("/{task_id}/reorder", response_model=TaskListResponse)
async def reorder_task(
    task_id: UUID,
    payload: TaskReorderRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskListResponse:
    tasks = await task_service.reorder_task(db, user, task_id, payload.new_position)
    return TaskListResponse(tasks=tasks)

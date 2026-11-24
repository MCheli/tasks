"""Task endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import API_KEY_HEADER, get_current_user
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.task import (
    OverviewResponse,
    TaskCreate,
    TaskCreateResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskNoteCreate,
    TaskNoteResponse,
    TaskReorderRequest,
    TaskUpdate,
    TaskUpdateResponse,
)
from app.services import task_service
from app.services.task_serializer import to_task_out_many

router = APIRouter()


@router.post("", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskCreateResponse:
    task = await task_service.create_task(db, user, payload)
    return TaskCreateResponse(task=task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    category: str | None = Query(None, pattern="^(personal|professional)$"),
    owner: str = Query("all", pattern="^(human|agent|all)$"),
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(open|completed|canceled|in_progress|blocked|done)$",
        description="open/completed/canceled, or an agent status; done = completed",
    ),
    q: str | None = Query(
        None, max_length=200, description="text match on title, notes, source, link"
    ),
    include_done: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskListResponse:
    """Flat list of tasks in the current cycle(s). Without `category` both lists are included;
    `owner` defaults to all. Open items only unless `include_done` or a `status` says otherwise."""
    rows = await task_service.list_tasks(
        db,
        user,
        category=category,
        owner=owner,
        status_filter=status_filter,
        query=q,
        include_done=include_done,
        limit=limit,
    )
    return TaskListResponse(tasks=await to_task_out_many(db, user, rows))


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverviewResponse:
    """All four lists in one call: {personal, professional} x {human, agent}, open items + counts."""
    return await task_service.overview(db, user)


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


async def _caller_name(request: Request, db: AsyncSession, user: User) -> str:
    """Default note author: the API key's name for programmatic callers, else the user."""
    raw = request.headers.get(API_KEY_HEADER)
    if raw:
        from sqlalchemy import select

        key = await db.scalar(select(ApiKey).where(ApiKey.key_hash == ApiKey.hash_key(raw)))
        if key:
            return key.name
    return user.display_name or user.email


@router.post(
    "/{task_id}/notes", response_model=TaskNoteResponse, status_code=status.HTTP_201_CREATED
)
async def add_note(
    task_id: UUID,
    payload: TaskNoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskNoteResponse:
    """Append a timestamped entry to the task's notes log."""
    author = payload.author or await _caller_name(request, db, user)
    note, task = await task_service.add_note(db, user, task_id, payload.body, author)
    return TaskNoteResponse(note=note, task=task)

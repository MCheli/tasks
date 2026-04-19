"""Task business logic — CRUD, soft delete, reorder, lineage detail."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle import Cycle
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    CycleLineageEntry,
    TaskCreate,
    TaskDetailResponse,
    TaskOut,
    TaskUpdate,
)
from app.services import cycle_service
from app.services.display_id_service import allocate_display_id
from app.services.task_serializer import (
    calculate_push_forward_count,
    to_task_out,
    to_task_out_many,
)

OPEN_STATUSES = ("open",)


async def _get_user_task(db: AsyncSession, user: User, task_id: UUID) -> Task:
    """Load a non-deleted task owned by the user, or 404."""
    task = await db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
        )
    )
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


async def _get_user_task_with_cycle(
    db: AsyncSession, user: User, task_id: UUID
) -> tuple[Task, Cycle]:
    task = await _get_user_task(db, user, task_id)
    cycle = await db.scalar(select(Cycle).where(Cycle.id == task.cycle_id))
    if not cycle:  # pragma: no cover  (FK guarantees this exists)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle not found")
    return task, cycle


async def create_task(db: AsyncSession, user: User, payload: TaskCreate) -> TaskOut:
    cycle = await cycle_service.get_or_create_current_cycle(db, user, payload.category)
    display_id = await allocate_display_id(db, user.id)

    max_pos = await db.scalar(
        select(func.coalesce(func.max(Task.position), -1)).where(
            Task.cycle_id == cycle.id,
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
            Task.status == "open",
        )
    )
    task = Task(
        persistent_task_id=uuid4(),
        display_id=display_id,
        user_id=user.id,
        cycle_id=cycle.id,
        previous_task_id=None,
        title=payload.title,
        notes=payload.notes,
        status="open",
        position=int(max_pos or 0) + 1 if max_pos is not None and max_pos >= 0 else 0,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return await to_task_out(db, user, task)


async def update_task(db: AsyncSession, user: User, task_id: UUID, payload: TaskUpdate) -> TaskOut:
    task, cycle = await _get_user_task_with_cycle(db, user, task_id)
    if cycle.ended_at is not None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Historical tasks are immutable; PATCH only the current cycle's tasks.",
        )

    now = datetime.now(UTC)

    if payload.title is not None:
        task.title = payload.title
    if payload.notes is not None:
        task.notes = payload.notes

    if payload.status is not None and payload.status != task.status:
        new_status = payload.status
        if new_status == "completed":
            task.status = "completed"
            task.completed_at = now
            task.canceled_at = None
        elif new_status == "canceled":
            task.status = "canceled"
            task.canceled_at = now
            task.completed_at = None
        elif new_status == "open":
            task.status = "open"
            task.completed_at = None
            task.canceled_at = None

    if payload.position is not None and payload.position != task.position:
        await _reorder_within_cycle(db, user, task, payload.position)

    await db.flush()
    await db.refresh(task)
    return await to_task_out(db, user, task)


async def soft_delete_lineage(db: AsyncSession, user: User, task_id: UUID) -> None:
    """Delete this task's entire lineage (every row sharing persistent_task_id)."""
    task = await _get_user_task(db, user, task_id)
    now = datetime.now(UTC)
    await db.execute(
        update(Task)
        .where(
            Task.user_id == user.id,
            Task.persistent_task_id == task.persistent_task_id,
            Task.deleted_at.is_(None),
        )
        .values(deleted_at=now, updated_at=now)
    )
    await db.flush()


async def reorder_task(
    db: AsyncSession, user: User, task_id: UUID, new_position: int
) -> list[TaskOut]:
    """Resequence the open list of the task's cycle.

    Returns the entire reordered open-task list (so the client can update
    state without a follow-up GET).
    """
    task, cycle = await _get_user_task_with_cycle(db, user, task_id)
    if cycle.ended_at is not None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cannot reorder tasks in a closed cycle.",
        )
    if task.status != "open":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only open tasks can be reordered.",
        )

    await _reorder_within_cycle(db, user, task, new_position)
    await db.flush()

    open_tasks = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.cycle_id == cycle.id,
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                    Task.status == "open",
                )
                .order_by(Task.position.asc())
            )
        ).scalars()
    )
    return await to_task_out_many(db, user, open_tasks)


async def _reorder_within_cycle(
    db: AsyncSession, user: User, task: Task, new_position: int
) -> None:
    """Compact open positions to a contiguous 0..N-1 with `task` placed at new_position."""
    open_tasks = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.cycle_id == task.cycle_id,
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                    Task.status == "open",
                )
                .order_by(Task.position.asc(), Task.created_at.asc())
            )
        ).scalars()
    )
    # Pull task out then reinsert at new_position (clamped).
    open_tasks = [t for t in open_tasks if t.id != task.id]
    new_position = max(0, min(new_position, len(open_tasks)))
    open_tasks.insert(new_position, task)
    for i, t in enumerate(open_tasks):
        if t.position != i:
            t.position = i


async def get_task_with_lineage(db: AsyncSession, user: User, task_id: UUID) -> TaskDetailResponse:
    task = await _get_user_task(db, user, task_id)

    # Walk the lineage by persistent_task_id (oldest → newest).
    lineage_rows = list(
        (
            await db.execute(
                select(Task, Cycle)
                .join(Cycle, Task.cycle_id == Cycle.id)
                .where(
                    Task.persistent_task_id == task.persistent_task_id,
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                )
                .order_by(Cycle.started_at.asc())
            )
        ).all()
    )

    lineage = [
        CycleLineageEntry(
            cycle_id=cycle.id,
            cycle_started_at=cycle.started_at,
            cycle_ended_at=cycle.ended_at,
            status_at_end=t.status,  # type: ignore[arg-type]
            position=t.position,
        )
        for t, cycle in lineage_rows
    ]
    pf = await calculate_push_forward_count(db, user.id, task.persistent_task_id)
    out = await to_task_out(db, user, task)
    return TaskDetailResponse(task=out, lineage=lineage, push_forward_count=pf)

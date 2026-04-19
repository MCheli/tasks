"""Helpers to convert ORM Task rows into TaskOut schemas with derived fields."""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskOut


async def calculate_push_forward_count(
    db: AsyncSession, user_id: UUID, persistent_task_id: UUID
) -> int:
    """Push-forward count = (rows in lineage) - 1, deleted excluded."""
    n = await db.scalar(
        select(func.count(Task.id)).where(
            Task.persistent_task_id == persistent_task_id,
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
        )
    )
    return max(0, int(n or 0) - 1)


def _task_to_dict(task: Task, push_forward_count: int) -> dict:
    return {
        "id": task.id,
        "persistent_task_id": task.persistent_task_id,
        "display_id": task.display_id,
        "cycle_id": task.cycle_id,
        "previous_task_id": task.previous_task_id,
        "title": task.title,
        "notes": task.notes,
        "status": task.status,
        "position": task.position,
        "push_forward_count": push_forward_count,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "completed_at": task.completed_at,
        "canceled_at": task.canceled_at,
    }


async def to_task_out(db: AsyncSession, user: User, task: Task) -> TaskOut:
    pf = await calculate_push_forward_count(db, user.id, task.persistent_task_id)
    return TaskOut.model_validate(_task_to_dict(task, pf))


async def to_task_out_many(
    db: AsyncSession, user: User, tasks: list[Task]
) -> list[TaskOut]:
    """Bulk variant — one COUNT query for all persistent_task_ids."""
    if not tasks:
        return []
    pids = list({t.persistent_task_id for t in tasks})
    rows = (
        await db.execute(
            select(Task.persistent_task_id, func.count(Task.id))
            .where(
                Task.user_id == user.id,
                Task.persistent_task_id.in_(pids),
                Task.deleted_at.is_(None),
            )
            .group_by(Task.persistent_task_id)
        )
    ).all()
    counts: dict[UUID, int] = defaultdict(int)
    for pid, n in rows:
        counts[pid] = max(0, int(n) - 1)
    return [
        TaskOut.model_validate(_task_to_dict(t, counts[t.persistent_task_id]))
        for t in tasks
    ]

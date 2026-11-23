"""Task business logic — CRUD, soft delete, reorder, lineage detail, notes log, flat queries."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle import Cycle
from app.models.task import Task, TaskNote
from app.models.user import User
from app.schemas.task import (
    CategoryBoard,
    CycleLineageEntry,
    OverviewResponse,
    OwnerBoard,
    TaskCreate,
    TaskDetailResponse,
    TaskNoteOut,
    TaskOut,
    TaskUpdate,
)
from app.services import cycle_service
from app.services.display_id_service import allocate_display_id
from app.services.owners import OWNERS, owner_clause
from app.services.task_serializer import (
    calculate_push_forward_count,
    to_task_out,
    to_task_out_many,
)

OPEN_STATUSES = ("open",)
CATEGORIES = ("personal", "professional")


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


async def find_by_display_id(db: AsyncSession, user: User, display_id: int) -> Task:
    """The current (newest, non-deleted) row of the lineage with this #number, or 404."""
    task = await db.scalar(
        select(Task)
        .join(Cycle, Cycle.id == Task.cycle_id)
        .where(
            Task.user_id == user.id,
            Task.display_id == display_id,
            Task.deleted_at.is_(None),
        )
        .order_by(Cycle.started_at.desc())
        .limit(1)
    )
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


# ---------------------------------------------------------------------------
# Status consistency for agent items
# ---------------------------------------------------------------------------


def _set_status(task: Task, new_status: str, now: datetime) -> None:
    if new_status == "completed":
        task.status = "completed"
        task.completed_at = now
        task.canceled_at = None
        if task.owner == "agent":
            task.agent_status = "done"
    elif new_status == "canceled":
        task.status = "canceled"
        task.canceled_at = now
        task.completed_at = None
    elif new_status == "open":
        task.status = "open"
        task.completed_at = None
        task.canceled_at = None
        if task.owner == "agent" and task.agent_status in (None, "done"):
            task.agent_status = "open"


def _set_agent_status(task: Task, agent_status: str, now: datetime) -> None:
    """Agent work state. done <-> completed; anything else reopens a completed item."""
    if task.owner != "agent":
        return
    if agent_status == "done":
        if task.status != "completed":
            _set_status(task, "completed", now)
        task.agent_status = "done"
        return
    task.agent_status = agent_status
    if task.status != "open":
        task.status = "open"
        task.completed_at = None
        task.canceled_at = None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_task(db: AsyncSession, user: User, payload: TaskCreate) -> TaskOut:
    cycle = await cycle_service.get_or_create_current_cycle(db, user, payload.category)
    display_id = await allocate_display_id(db, user.id)

    max_pos = await db.scalar(
        select(func.coalesce(func.max(Task.position), -1)).where(
            Task.cycle_id == cycle.id,
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
            Task.status == "open",
            Task.owner == payload.owner,
        )
    )
    agent_status = None
    if payload.owner == "agent":
        agent_status = payload.agent_status or "open"
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
        owner=payload.owner,
        source=payload.source,
        link=payload.link,
        agent_status=agent_status,
    )
    if agent_status == "done":
        _set_status(task, "completed", datetime.now(UTC))
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
    if payload.source is not None:
        task.source = payload.source
    if payload.link is not None:
        task.link = payload.link

    if payload.status is not None and payload.status != task.status:
        _set_status(task, payload.status, now)

    if payload.agent_status is not None:
        _set_agent_status(task, payload.agent_status, now)

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
    """Resequence the open list (of the task's owner) in the task's cycle.

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
                    Task.owner == task.owner,
                )
                .order_by(Task.position.asc())
            )
        ).scalars()
    )
    return await to_task_out_many(db, user, open_tasks)


async def _reorder_within_cycle(
    db: AsyncSession, user: User, task: Task, new_position: int
) -> None:
    """Compact open positions (same owner) to a contiguous 0..N-1 with `task` at new_position."""
    open_tasks = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.cycle_id == task.cycle_id,
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                    Task.status == "open",
                    Task.owner == task.owner,
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


# ---------------------------------------------------------------------------
# Notes log
# ---------------------------------------------------------------------------


async def list_notes(db: AsyncSession, user: User, persistent_task_id: UUID) -> list[TaskNoteOut]:
    rows = (
        await db.execute(
            select(TaskNote)
            .where(TaskNote.user_id == user.id, TaskNote.persistent_task_id == persistent_task_id)
            .order_by(TaskNote.created_at.asc())
        )
    ).scalars()
    return [TaskNoteOut.model_validate(n) for n in rows]


async def add_note(
    db: AsyncSession, user: User, task_id: UUID, body: str, author: str
) -> tuple[TaskNoteOut, TaskOut]:
    """Append to the task's notes log. Allowed on historical rows too (the log is per lineage)."""
    task = await _get_user_task(db, user, task_id)
    note = TaskNote(
        user_id=user.id,
        persistent_task_id=task.persistent_task_id,
        author=author.strip()[:200] or "unknown",
        body=body,
    )
    db.add(note)
    task.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(note)
    await db.refresh(task)
    return TaskNoteOut.model_validate(note), await to_task_out(db, user, task)


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
    notes_log = await list_notes(db, user, task.persistent_task_id)
    return TaskDetailResponse(task=out, lineage=lineage, push_forward_count=pf, notes_log=notes_log)


# ---------------------------------------------------------------------------
# Flat queries over the current cycles (REST GET /api/tasks, the MCP list_tasks tool,
# the overview for the ambient display)
# ---------------------------------------------------------------------------


async def _current_cycle_ids(db: AsyncSession, user: User, category: str | None) -> dict[str, UUID]:
    """Active cycle per category (only categories that have one; nothing is created)."""
    q = select(Cycle.category, Cycle.id).where(Cycle.user_id == user.id, Cycle.ended_at.is_(None))
    if category:
        q = q.where(Cycle.category == category)
    return {cat: cid for cat, cid in (await db.execute(q)).all()}


async def list_tasks(
    db: AsyncSession,
    user: User,
    *,
    category: str | None = None,
    owner: str = "all",
    status_filter: str | None = None,
    agent_status: str | None = None,
    query: str | None = None,
    include_done: bool = False,
    limit: int = 100,
) -> list[Task]:
    """Tasks in the current cycle(s), newest first within position order.

    status_filter: open | completed | canceled, or an agent status (open | in_progress |
    blocked | done). include_done=False hides completed and canceled items unless the status
    filter asks for them. query matches title, notes, source and link, case-insensitively.
    """
    cycles = await _current_cycle_ids(db, user, category)
    if not cycles:
        return []
    q = select(Task).where(
        Task.user_id == user.id,
        Task.cycle_id.in_(list(cycles.values())),
        Task.deleted_at.is_(None),
        owner_clause(owner),
    )
    if status_filter in ("completed", "canceled", "open"):
        q = q.where(Task.status == status_filter)
    elif status_filter in ("in_progress", "blocked"):
        q = q.where(Task.agent_status == status_filter)
    elif status_filter == "done":
        q = q.where(Task.status == "completed")
    elif status_filter:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status filter")
    elif not include_done:
        q = q.where(Task.status == "open")
    if agent_status:
        q = q.where(Task.agent_status == agent_status)
    if query and query.strip():
        needle = f"%{query.strip()}%"
        q = q.where(
            or_(
                Task.title.ilike(needle),
                Task.notes.ilike(needle),
                Task.source.ilike(needle),
                Task.link.ilike(needle),
            )
        )
    q = q.order_by(Task.status.asc(), Task.position.asc(), Task.created_at.asc()).limit(
        max(1, min(limit, 500))
    )
    return list((await db.execute(q)).scalars())


def _counts(tasks: list[Task], owner: str) -> dict[str, int]:
    counts = {"open": 0, "completed": 0, "canceled": 0}
    if owner == "agent":
        counts.update({"in_progress": 0, "blocked": 0})
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
        if owner == "agent" and t.status == "open" and t.agent_status in ("in_progress", "blocked"):
            counts[t.agent_status] += 1
    return counts


async def overview(db: AsyncSession, user: User) -> OverviewResponse:
    """Open items of all four lists plus counts, in one call (for the ambient display)."""
    cycles = await _current_cycle_ids(db, user, None)
    boards: dict[str, CategoryBoard] = {}
    for category in CATEGORIES:
        cycle_id = cycles.get(category)
        per_owner: dict[str, OwnerBoard] = {}
        for owner in OWNERS:
            rows: list[Task] = []
            if cycle_id:
                rows = list(
                    (
                        await db.execute(
                            select(Task)
                            .where(
                                Task.user_id == user.id,
                                Task.cycle_id == cycle_id,
                                Task.deleted_at.is_(None),
                                Task.owner == owner,
                            )
                            .order_by(Task.position.asc(), Task.created_at.asc())
                        )
                    ).scalars()
                )
            open_rows = [t for t in rows if t.status == "open"]
            per_owner[owner] = OwnerBoard(
                open=await to_task_out_many(db, user, open_rows),
                counts=_counts(rows, owner),
            )
        boards[category] = CategoryBoard(
            cycle_id=cycle_id, human=per_owner["human"], agent=per_owner["agent"]
        )
    return OverviewResponse(personal=boards["personal"], professional=boards["professional"])

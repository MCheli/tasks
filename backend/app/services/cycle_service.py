"""Cycle business logic.

Transition logic lives here too but is exercised in Phase 3 tests.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle import Cycle
from app.models.task import Task
from app.models.user import User
from app.schemas.cycle import (
    CycleDetail,
    CycleListItem,
    CycleListResponse,
    CycleOut,
    CycleSummary,
    TransitionAction,
    TransitionResponse,
    TransitionSummary,
)
from app.schemas.task import TaskOut
from app.services.task_serializer import to_task_out_many

VALID_CATEGORIES = ("personal", "professional")


def _check_category(category: str) -> None:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"category must be one of {VALID_CATEGORIES}",
        )


async def get_or_create_current_cycle(
    db: AsyncSession, user: User, category: str
) -> Cycle:
    """Return the user's active cycle in this category, creating one if needed."""
    _check_category(category)
    existing = await db.scalar(
        select(Cycle).where(
            Cycle.user_id == user.id,
            Cycle.category == category,
            Cycle.ended_at.is_(None),
        )
    )
    if existing:
        return existing

    cycle = Cycle(user_id=user.id, category=category)
    db.add(cycle)
    await db.flush()
    await db.refresh(cycle)
    return cycle


async def get_cycle(db: AsyncSession, user: User, cycle_id: UUID) -> Cycle:
    """Load a cycle owned by the user or raise 404."""
    cycle = await db.scalar(
        select(Cycle).where(Cycle.id == cycle_id, Cycle.user_id == user.id)
    )
    if not cycle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle not found")
    return cycle


async def _load_cycle_tasks(
    db: AsyncSession, user: User, cycle: Cycle
) -> dict[str, list[Task]]:
    """Return tasks for a cycle, grouped by status. Excludes deleted rows.

    Sort: position ASC within each group.
    """
    result = await db.execute(
        select(Task)
        .where(
            Task.cycle_id == cycle.id,
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
        )
        .order_by(Task.position.asc(), Task.created_at.asc())
    )
    grouped: dict[str, list[Task]] = {"open": [], "completed": [], "canceled": []}
    for t in result.scalars():
        grouped.setdefault(t.status, []).append(t)
    return grouped


async def cycle_detail(db: AsyncSession, user: User, cycle: Cycle) -> CycleDetail:
    grouped = await _load_cycle_tasks(db, user, cycle)
    out: dict[str, list[TaskOut]] = {
        "open": await to_task_out_many(db, user, grouped["open"]),
        "completed": await to_task_out_many(db, user, grouped["completed"]),
        "canceled": await to_task_out_many(db, user, grouped["canceled"]),
    }
    summary = CycleSummary(
        open=len(grouped["open"]),
        completed=len(grouped["completed"]),
        canceled=len(grouped["canceled"]),
    )
    return CycleDetail(
        cycle=CycleOut.model_validate(cycle),
        tasks=out,
        summary=summary,
    )


async def list_cycles(
    db: AsyncSession,
    user: User,
    category: str,
    limit: int = 50,
    offset: int = 0,
) -> CycleListResponse:
    _check_category(category)
    cycles_q = (
        select(Cycle)
        .where(Cycle.user_id == user.id, Cycle.category == category)
        .order_by(Cycle.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    cycle_rows = list((await db.execute(cycles_q)).scalars())

    total = await db.scalar(
        select(func.count(Cycle.id)).where(
            Cycle.user_id == user.id, Cycle.category == category
        )
    ) or 0

    if not cycle_rows:
        return CycleListResponse(cycles=[], total=int(total))

    # Single grouped count query for the page of cycles.
    counts_q = (
        select(Task.cycle_id, Task.status, func.count(Task.id))
        .where(
            Task.cycle_id.in_([c.id for c in cycle_rows]),
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
        )
        .group_by(Task.cycle_id, Task.status)
    )
    counts: dict[UUID, dict[str, int]] = defaultdict(
        lambda: {"open": 0, "completed": 0, "canceled": 0}
    )
    for cycle_id, st, n in (await db.execute(counts_q)).all():
        counts[cycle_id][st] = n

    items = [
        CycleListItem(
            **CycleOut.model_validate(c).model_dump(),
            task_counts=CycleSummary(**counts[c.id]),
        )
        for c in cycle_rows
    ]
    return CycleListResponse(cycles=items, total=int(total))


# ---------------------------------------------------------------------------
# Transition (Phase 3 surface)
# ---------------------------------------------------------------------------


async def transition_cycle(
    db: AsyncSession,
    user: User,
    cycle_id: UUID,
    actions: list[TransitionAction],
) -> TransitionResponse:
    """Close `cycle_id` and create a new active cycle for the same category."""
    old_cycle = await db.scalar(
        select(Cycle).where(Cycle.id == cycle_id, Cycle.user_id == user.id)
    )
    if not old_cycle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle not found")
    if old_cycle.ended_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cycle is already closed")

    open_tasks = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.cycle_id == old_cycle.id,
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                    Task.status == "open",
                )
                .order_by(Task.position.asc())
            )
        ).scalars()
    )

    action_by_pid: dict[UUID, str] = {a.persistent_task_id: a.action for a in actions}
    open_pids = {t.persistent_task_id for t in open_tasks}

    # Validate every open task has an action.
    missing = open_pids - set(action_by_pid.keys())
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Missing action for {len(missing)} open task(s)",
        )
    # Reject actions targeting tasks not in this cycle's open set.
    extra = set(action_by_pid.keys()) - open_pids
    if extra:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Actions reference tasks that are not open in this cycle",
        )

    now = datetime.now(timezone.utc)
    forwarded_count = completed_count = canceled_count = 0

    # 1. Resolve old cycle rows.
    for t in open_tasks:
        action = action_by_pid[t.persistent_task_id]
        if action == "complete":
            t.status = "completed"
            t.completed_at = now
            completed_count += 1
        elif action == "cancel":
            t.status = "canceled"
            t.canceled_at = now
            canceled_count += 1
        # forward → leave the old row open; it stays in old_cycle as the
        # "what was forwarded" snapshot.

    # 2. Close the old cycle FIRST so the partial-unique index
    #    (one active cycle per user+category) doesn't fire on the new insert.
    old_cycle.ended_at = now
    await db.flush()

    # 3. Create the new cycle and link them.
    new_cycle = Cycle(
        user_id=user.id,
        category=old_cycle.category,
        started_at=now,
    )
    db.add(new_cycle)
    await db.flush()
    old_cycle.next_cycle_id = new_cycle.id

    # 4. Create forwarded task rows in the new cycle.
    forwarded_tasks: list[Task] = []
    for t in open_tasks:
        if action_by_pid[t.persistent_task_id] != "forward":
            continue
        new_task = Task(
            persistent_task_id=t.persistent_task_id,
            display_id=t.display_id,
            user_id=user.id,
            cycle_id=new_cycle.id,
            previous_task_id=t.id,
            title=t.title,
            notes=t.notes,
            status="open",
            position=t.position,
        )
        # The "forward" semantic for the OLD row: we mark it completed-equivalent
        # by leaving status='open' but the cycle is now closed. The task is
        # visible in history as a forwarded row via previous_task_id linkage.
        db.add(new_task)
        forwarded_tasks.append(new_task)
        forwarded_count += 1

    await db.flush()

    out = {
        "open": await to_task_out_many(db, user, forwarded_tasks),
        "completed": [],
        "canceled": [],
    }
    return TransitionResponse(
        old_cycle=CycleOut.model_validate(old_cycle),
        new_cycle=CycleOut.model_validate(new_cycle),
        new_cycle_tasks=out,
        summary=TransitionSummary(
            forwarded=forwarded_count,
            completed=completed_count,
            canceled=canceled_count,
        ),
    )

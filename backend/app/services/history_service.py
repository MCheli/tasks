"""Build the lineage shape consumed by the Gantt-style HistoryView."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cycle import Cycle
from app.models.task import Task
from app.models.user import User
from app.schemas.history import (
    CycleBoundary,
    HistoryResponse,
    Lineage,
    LineageSpan,
)


async def get_history(
    db: AsyncSession, user: User, category: str
) -> HistoryResponse:
    cycles = list(
        (
            await db.execute(
                select(Cycle)
                .where(Cycle.user_id == user.id, Cycle.category == category)
                .order_by(Cycle.started_at.asc())
            )
        ).scalars()
    )
    if not cycles:
        return HistoryResponse(cycles=[], lineages=[])

    rows = list(
        (
            await db.execute(
                select(Task, Cycle)
                .join(Cycle, Cycle.id == Task.cycle_id)
                .where(
                    Task.user_id == user.id,
                    Cycle.category == category,
                    Task.deleted_at.is_(None),
                )
                .order_by(Cycle.started_at.asc())
            )
        ).all()
    )

    by_pid: dict = defaultdict(list)
    for task, cycle in rows:
        by_pid[task.persistent_task_id].append((task, cycle))

    now = datetime.now(timezone.utc)
    lineages: list[Lineage] = []
    for pid, items in by_pid.items():
        items.sort(key=lambda tc: tc[1].started_at)
        latest_task, latest_cycle = items[-1]
        first_task, first_cycle = items[0]
        spans = [
            LineageSpan(
                cycle_id=cycle.id,
                started_at=cycle.started_at,
                ended_at=cycle.ended_at,
                status_at_end=task.status,  # type: ignore[arg-type]
            )
            for task, cycle in items
        ]
        last_seen = (
            latest_cycle.ended_at
            if latest_task.status != "open" and latest_cycle.ended_at
            else (latest_cycle.ended_at or now)
        )
        lineages.append(
            Lineage(
                persistent_task_id=pid,
                display_id=latest_task.display_id,
                title=latest_task.title,
                latest_status=latest_task.status,  # type: ignore[arg-type]
                first_seen_at=first_cycle.started_at,
                last_seen_at=last_seen,
                push_forward_count=max(0, len(items) - 1),
                spans=spans,
            )
        )
    # Oldest lineages at top.
    lineages.sort(key=lambda l: l.first_seen_at)

    return HistoryResponse(
        cycles=[CycleBoundary.model_validate(c) for c in cycles],
        lineages=lineages,
    )

"""The demo seed is one coherent simulation, whatever day it runs."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.cycle import Cycle
from app.models.task import Task
from app.models.user import User
from app.services.demo_seed import seed_demo
from app.services.history_service import get_history

# Every month, and every weekday, at the nightly restart time (08:30 UTC).
DAYS = [datetime(2026, m, 3 + m, 8, 30, tzinfo=UTC) for m in range(1, 13)] + [
    datetime(2026, 10, 26, 8, 30, tzinfo=UTC) + timedelta(days=d) for d in range(7)
]


@pytest.mark.parametrize("now", DAYS, ids=lambda d: d.strftime("%b%d-%a"))
async def test_seed_is_coherent(db, now):
    counts = await seed_demo(db, now=now)
    user = await db.scalar(select(User).where(User.email == "claudius@tasks.dev"))
    assert user.display_name == "Claudius Banks"
    assert counts["lineages"] > 80

    cycles = list(
        (await db.execute(select(Cycle).where(Cycle.user_id == user.id).order_by(Cycle.started_at)))
        .scalars()
        .all()
    )
    tasks = list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all())
    by_id = {t.id: t for t in tasks}
    cycle_by_id = {c.id: c for c in cycles}

    for category in ("personal", "professional"):
        chain = [c for c in cycles if c.category == category]
        assert [c.ended_at is None for c in chain].count(True) == 1
        assert chain[-1].ended_at is None
        for a, b in zip(chain, chain[1:], strict=False):
            assert a.ended_at == b.started_at and a.next_cycle_id == b.id
        assert now - timedelta(days=17) < chain[-1].started_at < now - timedelta(days=2)

    successors = defaultdict(list)
    for t in tasks:
        if t.previous_task_id:
            successors[t.previous_task_id].append(t)
    for t in tasks:
        cycle = cycle_by_id[t.cycle_id]
        for stamp in (t.created_at, t.updated_at, t.completed_at, t.canceled_at):
            assert stamp is None or stamp <= now, t.title
        assert cycle.started_at <= t.created_at, t.title
        if t.completed_at:
            assert t.status == "completed" and t.created_at < t.completed_at, t.title
            assert cycle.ended_at is None or t.completed_at <= cycle.ended_at, t.title
        if t.status == "open" and cycle.ended_at and not t.deleted_at:
            # forwarded: the next cycle has exactly one row continuing it
            (nxt,) = successors[t.id]
            assert nxt.cycle_id == cycle.next_cycle_id and nxt.display_id == t.display_id
        if t.previous_task_id:
            prev = by_id[t.previous_task_id]
            assert prev.persistent_task_id == t.persistent_task_id and prev.status == "open"

    lineage_ids = defaultdict(set)
    for t in tasks:
        lineage_ids[t.display_id].add(t.persistent_task_id)
    assert all(len(p) == 1 for p in lineage_ids.values())

    # Believable completion: most past items done, a few carried, some dropped.
    past = [t for t in tasks if cycle_by_id[t.cycle_id].ended_at and not t.deleted_at]
    done = sum(t.status == "completed" for t in past) / len(past)
    assert 0.55 < done < 0.9, done
    assert any(t.status == "canceled" for t in past)
    assert max(len(lineage) for lineage in _lineages(tasks).values()) >= 4

    history = await get_history(db, user, "personal")
    assert len(history.cycles) == 11 and len(history.lineages) > 40


def _lineages(tasks):
    out = defaultdict(list)
    for t in tasks:
        out[t.persistent_task_id].append(t)
    return out

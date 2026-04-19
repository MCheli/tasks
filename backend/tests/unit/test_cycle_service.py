"""Unit tests for cycle_service: auto-create, get, list, transition logic."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.schemas.cycle import TransitionAction
from app.schemas.task import TaskCreate
from app.services import cycle_service, task_service


async def test_auto_create_current_cycle(db, test_user):
    c = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    assert c.ended_at is None
    assert c.category == "personal"


async def test_returns_same_active_cycle(db, test_user):
    a = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    b = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    assert a.id == b.id


async def test_personal_and_professional_independent(db, test_user):
    p = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    w = await cycle_service.get_or_create_current_cycle(db, test_user, "professional")
    assert p.id != w.id


async def test_transition_forward_creates_lineage(db, test_user):
    t = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="A")
    )
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    res = await cycle_service.transition_cycle(
        db,
        test_user,
        cycle.id,
        [TransitionAction(persistent_task_id=t.persistent_task_id, action="forward")],
    )
    assert res.summary.forwarded == 1
    assert res.summary.completed == 0
    forwarded = res.new_cycle_tasks["open"][0]
    assert forwarded.persistent_task_id == t.persistent_task_id
    assert forwarded.previous_task_id == t.id


async def test_transition_complete_and_cancel(db, test_user):
    a = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="A")
    )
    b = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="B")
    )
    c = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="C")
    )
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    res = await cycle_service.transition_cycle(
        db,
        test_user,
        cycle.id,
        [
            TransitionAction(persistent_task_id=a.persistent_task_id, action="forward"),
            TransitionAction(persistent_task_id=b.persistent_task_id, action="complete"),
            TransitionAction(persistent_task_id=c.persistent_task_id, action="cancel"),
        ],
    )
    assert res.summary == res.summary.__class__(forwarded=1, completed=1, canceled=1)
    assert res.old_cycle.ended_at is not None
    assert res.new_cycle.ended_at is None


async def test_transition_missing_action_rejected(db, test_user):
    a = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="A")
    )
    b = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="B")
    )
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    with pytest.raises(HTTPException) as exc:
        await cycle_service.transition_cycle(
            db,
            test_user,
            cycle.id,
            [TransitionAction(persistent_task_id=a.persistent_task_id, action="forward")],
        )
    assert exc.value.status_code == 400


async def test_transition_already_closed(db, test_user):
    t = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="A")
    )
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    await cycle_service.transition_cycle(
        db,
        test_user,
        cycle.id,
        [TransitionAction(persistent_task_id=t.persistent_task_id, action="forward")],
    )
    # Old cycle is closed → transitioning it again is a 409.
    with pytest.raises(HTTPException) as exc:
        await cycle_service.transition_cycle(db, test_user, cycle.id, [])
    assert exc.value.status_code == 409


async def test_push_forward_count_grows(db, test_user):
    t = await task_service.create_task(
        db, test_user, TaskCreate(category="personal", title="X")
    )
    pid = t.persistent_task_id

    # 1st transition: forward.
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    await cycle_service.transition_cycle(
        db,
        test_user,
        cycle.id,
        [TransitionAction(persistent_task_id=pid, action="forward")],
    )

    # 2nd transition.
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    await cycle_service.transition_cycle(
        db,
        test_user,
        cycle.id,
        [TransitionAction(persistent_task_id=pid, action="forward")],
    )

    # Now there should be 3 rows (orig + 2 forwards). push_forward = 3 - 1 = 2.
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    detail = await cycle_service.cycle_detail(db, test_user, cycle)
    open_tasks = detail.tasks["open"]
    assert len(open_tasks) == 1
    assert open_tasks[0].push_forward_count == 2

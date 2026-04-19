"""Unit tests for task_service: create, update, delete, reorder, lineage."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.schemas.task import TaskCreate, TaskUpdate
from app.services import cycle_service, task_service


async def test_create_task_creates_cycle_and_assigns_display_id(db, test_user):
    t1 = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="A"))
    assert t1.title == "A"
    assert t1.status == "open"
    assert t1.display_id == 1
    assert t1.position == 0

    t2 = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="B"))
    assert t2.display_id == 2
    assert t2.position == 1


async def test_categories_isolated(db, test_user):
    p = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="P"))
    pro = await task_service.create_task(
        db, test_user, TaskCreate(category="professional", title="W")
    )
    assert p.cycle_id != pro.cycle_id


async def test_update_task_status_completed_sets_timestamp(db, test_user):
    t = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="X"))
    out = await task_service.update_task(db, test_user, t.id, TaskUpdate(status="completed"))
    assert out.status == "completed"
    assert out.completed_at is not None
    assert out.canceled_at is None


async def test_update_task_status_canceled_sets_timestamp(db, test_user):
    t = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="X"))
    out = await task_service.update_task(db, test_user, t.id, TaskUpdate(status="canceled"))
    assert out.status == "canceled"
    assert out.canceled_at is not None
    assert out.completed_at is None


async def test_update_back_to_open_clears_timestamps(db, test_user):
    t = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="X"))
    await task_service.update_task(db, test_user, t.id, TaskUpdate(status="completed"))
    out = await task_service.update_task(db, test_user, t.id, TaskUpdate(status="open"))
    assert out.status == "open"
    assert out.completed_at is None


async def test_soft_delete_hides_task(db, test_user):
    t = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="X"))
    await task_service.soft_delete_lineage(db, test_user, t.id)
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")
    detail = await cycle_service.cycle_detail(db, test_user, cycle)
    assert detail.summary.open == 0


async def test_reorder_resequences_open_tasks(db, test_user):
    a = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="A"))
    b = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="B"))
    c = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="C"))
    # Move C to the top.
    out = await task_service.reorder_task(db, test_user, c.id, 0)
    titles = [t.title for t in out]
    assert titles == ["C", "A", "B"]
    positions = [t.position for t in out]
    assert positions == [0, 1, 2]


async def test_user_isolation(db, test_user, other_user):
    t = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="Mine"))
    with pytest.raises(HTTPException) as exc:
        await task_service.get_task_with_lineage(db, other_user, t.id)
    assert exc.value.status_code == 404

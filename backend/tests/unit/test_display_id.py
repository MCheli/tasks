"""Unit tests for the per-user display_id allocator."""

from __future__ import annotations

from app.services.display_id_service import allocate_display_id


async def test_starts_at_one(db, test_user):
    assert await allocate_display_id(db, test_user.id) == 1


async def test_increments(db, test_user):
    a = await allocate_display_id(db, test_user.id)
    b = await allocate_display_id(db, test_user.id)
    c = await allocate_display_id(db, test_user.id)
    assert (a, b, c) == (1, 2, 3)


async def test_per_user_independent(db, test_user, other_user):
    assert await allocate_display_id(db, test_user.id) == 1
    assert await allocate_display_id(db, other_user.id) == 1
    assert await allocate_display_id(db, test_user.id) == 2
    assert await allocate_display_id(db, other_user.id) == 2

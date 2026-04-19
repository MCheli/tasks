"""Per-user incrementing display_id allocator."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UPSERT_RETURNING = text(
    """
    INSERT INTO display_id_sequences (user_id, next_value)
    VALUES (:user_id, 2)
    ON CONFLICT (user_id) DO UPDATE
      SET next_value = display_id_sequences.next_value + 1
    RETURNING next_value - 1 AS allocated
"""
)


async def allocate_display_id(db: AsyncSession, user_id: UUID) -> int:
    """Atomically allocate the next display_id for the given user.

    First call returns 1, subsequent calls increment.
    """
    result = await db.execute(_UPSERT_RETURNING, {"user_id": user_id})
    return int(result.scalar_one())

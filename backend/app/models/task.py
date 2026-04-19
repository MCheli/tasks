"""Task and DisplayIdSequence models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    # Per-cycle row identity.
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Stable identity across the task's lineage (forward-carries share this UUID).
    persistent_task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    # Per-user incrementing integer (e.g. #42).
    display_id: Mapped[int] = mapped_column(Integer, nullable=False)

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cycle: Mapped["Cycle"] = relationship(back_populates="tasks")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','completed','canceled')", name="ck_tasks_status"
        ),
        # display_id is unique per *lineage* (persistent_task_id), not per row.
        # The spec text said per-user-unique, but a forwarded row shares the
        # display_id with its predecessor, so per-row uniqueness is impossible.
        # Keep an index for lookup performance; uniqueness is enforced
        # implicitly by allocate_display_id always issuing a fresh integer
        # and by every new persistent_task_id getting one allocation.
        Index("ix_tasks_user_display_id", "user_id", "display_id"),
        Index(
            "ix_tasks_cycle_filter",
            "cycle_id",
            "deleted_at",
            "status",
            "position",
        ),
        Index("ix_tasks_lineage", "user_id", "persistent_task_id"),
        Index("ix_tasks_previous", "previous_task_id"),
    )


class DisplayIdSequence(Base):
    """Per-user counter for tasks.display_id."""

    __tablename__ = "display_id_sequences"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

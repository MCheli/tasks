"""Task, TaskNote and DisplayIdSequence models."""

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

# Who a task belongs to within a list: Mark's own to-do ("human") or the agents' follow-up
# list ("agent"). Every row that existed before the split is "human".
OWNERS = ("human", "agent")
# Work state of an agent item. "done" always goes together with status="completed"
# (task_service keeps the two in step), so a done agent item behaves like any completed task.
AGENT_STATUSES = ("open", "in_progress", "blocked", "done")


class Task(Base):
    __tablename__ = "tasks"

    # Per-cycle row identity.
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Stable identity across the task's lineage (forward-carries share this UUID).
    persistent_task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
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

    # Agent-list fields. owner is "human" for Mark's own items (and for everything created
    # without saying otherwise); the rest are only meaningful when owner == "agent".
    owner: Mapped[str] = mapped_column(
        String(10), nullable=False, default="human", server_default="human"
    )
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    link: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    agent_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cycle: Mapped[Cycle] = relationship(back_populates="tasks")  # noqa: F821

    __table_args__ = (
        CheckConstraint("status IN ('open','completed','canceled')", name="ck_tasks_status"),
        CheckConstraint("owner IN ('human','agent')", name="ck_tasks_owner"),
        CheckConstraint(
            "agent_status IS NULL OR agent_status IN ('open','in_progress','blocked','done')",
            name="ck_tasks_agent_status",
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
        Index("ix_tasks_cycle_owner", "cycle_id", "owner", "deleted_at", "status"),
        Index("ix_tasks_lineage", "user_id", "persistent_task_id"),
        Index("ix_tasks_previous", "previous_task_id"),
    )


class TaskNote(Base):
    """One entry in a task's notes log (who said what, when).

    Attached to the lineage (persistent_task_id), so the log follows a task when a cycle
    transition forwards it into a new row.
    """

    __tablename__ = "task_notes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    persistent_task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Who wrote it: a routine, thread or session name for agents; the user's name for Mark.
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_task_notes_lineage", "user_id", "persistent_task_id", "created_at"),
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

"""Cycle model — a planning interval per (user, category)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_cycle_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cycles.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="cycle",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("category IN ('personal','professional')", name="ck_cycles_category"),
        Index("ix_cycles_user_cat_ended", "user_id", "category", "ended_at"),
        Index("ix_cycles_user_cat_started", "user_id", "category", "started_at"),
        # Enforce: only one active cycle per (user, category).
        Index(
            "uq_cycles_user_cat_active",
            "user_id",
            "category",
            unique=True,
            postgresql_where="ended_at IS NULL",
        ),
    )

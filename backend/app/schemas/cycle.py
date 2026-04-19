"""Cycle-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.task import TaskOut

Category = Literal["personal", "professional"]


class CycleSummary(BaseModel):
    open: int = 0
    completed: int = 0
    canceled: int = 0


class CycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: Category
    started_at: datetime
    ended_at: datetime | None
    next_cycle_id: UUID | None


class CycleListItem(CycleOut):
    task_counts: CycleSummary


class CycleDetail(BaseModel):
    cycle: CycleOut
    tasks: dict[Literal["open", "completed", "canceled"], list[TaskOut]]
    summary: CycleSummary


class CycleListResponse(BaseModel):
    cycles: list[CycleListItem]
    total: int


class TransitionAction(BaseModel):
    persistent_task_id: UUID
    action: Literal["forward", "complete", "cancel"]


class TransitionRequest(BaseModel):
    actions: list[TransitionAction] = Field(default_factory=list)


class TransitionSummary(BaseModel):
    forwarded: int
    completed: int
    canceled: int


class TransitionResponse(BaseModel):
    old_cycle: CycleOut
    new_cycle: CycleOut
    new_cycle_tasks: dict[Literal["open", "completed", "canceled"], list[TaskOut]]
    summary: TransitionSummary

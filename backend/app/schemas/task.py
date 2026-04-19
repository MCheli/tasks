"""Task Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["personal", "professional"]
Status = Literal["open", "completed", "canceled"]


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = None


class TaskCreate(TaskBase):
    category: Category


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = None
    status: Status | None = None
    position: int | None = Field(default=None, ge=0)


class TaskReorderRequest(BaseModel):
    new_position: int = Field(..., ge=0)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persistent_task_id: UUID
    display_id: int
    cycle_id: UUID
    previous_task_id: UUID | None
    title: str
    notes: str | None
    status: Status
    position: int
    push_forward_count: int  # derived; injected by service layer
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    canceled_at: datetime | None


class TaskCreateResponse(BaseModel):
    task: TaskOut


class TaskUpdateResponse(BaseModel):
    task: TaskOut


class TaskListResponse(BaseModel):
    tasks: list[TaskOut]


class CycleLineageEntry(BaseModel):
    cycle_id: UUID
    cycle_started_at: datetime
    cycle_ended_at: datetime | None
    status_at_end: Status
    position: int


class TaskDetailResponse(BaseModel):
    task: TaskOut
    lineage: list[CycleLineageEntry]
    push_forward_count: int

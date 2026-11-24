"""Task Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["personal", "professional"]
Status = Literal["open", "completed", "canceled"]
# Mark's own list ("human") or the agents' follow-up list ("agent"); "all" is a query value.
Owner = Literal["human", "agent"]
OwnerFilter = Literal["human", "agent", "all"]
# Work state of an agent item. "done" <-> status "completed" (kept in step by the service).
AgentStatus = Literal["open", "in_progress", "blocked", "done"]

# The column is TEXT; the cap only bounds what one request can store.
NOTES_MAX_LENGTH = 20_000
SOURCE_MAX_LENGTH = 200
LINK_MAX_LENGTH = 2000


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)


class TaskCreate(TaskBase):
    category: Category
    # Everything that doesn't say otherwise is one of Mark's own items (the Chore tracker and
    # the UI never send this field).
    owner: Owner = "human"
    source: str | None = Field(default=None, max_length=SOURCE_MAX_LENGTH)
    link: str | None = Field(default=None, max_length=LINK_MAX_LENGTH)
    agent_status: AgentStatus | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)
    status: Status | None = None
    position: int | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, max_length=SOURCE_MAX_LENGTH)
    link: str | None = Field(default=None, max_length=LINK_MAX_LENGTH)
    # Agent items only: open / in_progress / blocked / done. "done" completes the task and
    # completing an agent task marks it done.
    agent_status: AgentStatus | None = None


class TaskReorderRequest(BaseModel):
    new_position: int = Field(..., ge=0)


class TaskNoteCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=NOTES_MAX_LENGTH)
    # Who is writing: a routine, thread or session name. Defaults to the caller's identity
    # (the API key's name, or the signed-in user).
    author: str | None = Field(default=None, max_length=SOURCE_MAX_LENGTH)


class TaskNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author: str
    body: str
    created_at: datetime


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
    owner: Owner
    source: str | None
    link: str | None
    agent_status: AgentStatus | None
    note_count: int  # derived; entries in the notes log
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


class TaskNoteResponse(BaseModel):
    note: TaskNoteOut
    task: TaskOut


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
    notes_log: list[TaskNoteOut] = Field(default_factory=list)


class OwnerBoard(BaseModel):
    """One list's items for one owner, from the current cycle."""

    open: list[TaskOut]
    counts: dict[str, int]  # open / completed / canceled, plus agent statuses for agents


class CategoryBoard(BaseModel):
    cycle_id: UUID | None
    human: OwnerBoard
    agent: OwnerBoard


class OverviewResponse(BaseModel):
    """All four lists in one call: {personal, professional} x {human, agent}."""

    personal: CategoryBoard
    professional: CategoryBoard

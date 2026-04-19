"""Schemas for the /api/history Gantt endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


Status = Literal["open", "completed", "canceled"]


class CycleBoundary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    ended_at: datetime | None


class LineageSpan(BaseModel):
    cycle_id: UUID
    started_at: datetime
    ended_at: datetime | None
    status_at_end: Status


class Lineage(BaseModel):
    persistent_task_id: UUID
    display_id: int
    title: str
    latest_status: Status
    first_seen_at: datetime
    last_seen_at: datetime
    push_forward_count: int
    spans: list[LineageSpan]


class HistoryResponse(BaseModel):
    cycles: list[CycleBoundary]
    lineages: list[Lineage]

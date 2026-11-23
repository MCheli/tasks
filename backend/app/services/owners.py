"""The owner dimension shared by the task queries: Mark's list ("human") vs the agents' list."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models.task import Task

OWNERS = ("human", "agent")


def owner_clause(owner: str | None):
    """SQL filter for an owner query value: human (the default), agent or all."""
    if owner in (None, "human"):
        return Task.owner == "human"
    if owner == "agent":
        return Task.owner == "agent"
    if owner == "all":
        return True
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "owner must be human, agent or all")

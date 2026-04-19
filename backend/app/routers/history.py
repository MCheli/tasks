"""History endpoint — Gantt-shaped lineage data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.history import HistoryResponse
from app.services import history_service

router = APIRouter()


@router.get("", response_model=HistoryResponse)
async def get_history(
    category: str = Query(..., pattern="^(personal|professional)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryResponse:
    return await history_service.get_history(db, user, category)

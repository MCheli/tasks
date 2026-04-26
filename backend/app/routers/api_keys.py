"""API key management endpoints (per-user, owner-scoped)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter()


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiKeyCreated:
    raw = ApiKey.generate_key()
    record = ApiKey(
        user_id=user.id,
        name=payload.name.strip(),
        key_prefix=raw[:12],
        key_hash=ApiKey.hash_key(raw),
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return ApiKeyCreated(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        is_active=record.is_active,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
        key=raw,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    await db.delete(record)

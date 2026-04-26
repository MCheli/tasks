"""FastAPI dependencies — get_db, get_current_user."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User

SESSION_COOKIE = "session"
API_KEY_HEADER = "X-API-Key"


async def get_current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current user from an X-API-Key header or session cookie.

    The header is checked first so programmatic clients aren't forced to also
    clear cookies. Either path returns the owning User; both raise 401 on
    failure with no information about which method failed.
    """
    if x_api_key:
        return await _user_from_api_key(db, x_api_key)

    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(session)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def _user_from_api_key(db: AsyncSession, raw: str) -> User:
    if not raw.startswith(ApiKey.KEY_PREFIX):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    key_hash = ApiKey.hash_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")

    user_result = await db.execute(select(User).where(User.id == record.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")

    record.last_used_at = datetime.now(timezone.utc)
    return user

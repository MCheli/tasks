"""Password hashing and JWT helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt only — keep it simple, matches AGENT_INSTRUCTIONS direction.
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return pwd_ctx.verify(password, hashed)
    except ValueError:
        # Malformed hash, etc.
        return False


@dataclass(frozen=True)
class SessionToken:
    user_id: UUID
    issued_at: int
    expires_at: int
    auth_time: int  # when the user signed in; refreshes keep it


def _expiry(now: int, auth_time: int) -> int:
    return min(
        now + int(timedelta(days=settings.JWT_EXPIRE_DAYS).total_seconds()),
        auth_time + int(timedelta(days=settings.JWT_MAX_SESSION_DAYS).total_seconds()),
    )


def create_access_token(user_id: UUID, auth_time: int | None = None) -> str:
    now = int(datetime.now(UTC).timestamp())
    auth_time = now if auth_time is None else auth_time
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": _expiry(now, auth_time),
        "auth_time": auth_time,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_session_token(token: str) -> SessionToken | None:
    """Return the token's claims, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        issued_at = int(payload["iat"])
        return SessionToken(
            user_id=UUID(payload["sub"]),
            issued_at=issued_at,
            expires_at=int(payload["exp"]),
            # Tokens from before auth_time existed: treat the issue time as the sign-in time.
            auth_time=int(payload.get("auth_time", issued_at)),
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None


def decode_access_token(token: str) -> UUID | None:
    """Return the user_id encoded in the token, or None if invalid/expired."""
    session = decode_session_token(token)
    return session.user_id if session else None


def refreshed_access_token(session: SessionToken) -> str | None:
    """Return a renewed token for this session, or None if it isn't due or can't be extended."""
    now = int(datetime.now(UTC).timestamp())
    refresh_after = int(timedelta(hours=settings.JWT_REFRESH_AFTER_HOURS).total_seconds())
    if now - session.issued_at < refresh_after:
        return None
    if _expiry(now, session.auth_time) <= session.expires_at:
        return None  # already at the session's hard limit
    return create_access_token(session.user_id, auth_time=session.auth_time)

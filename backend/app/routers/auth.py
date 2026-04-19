"""Authentication routes — login, logout, me, Google OAuth scaffolds."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.oauth import is_google_configured
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.dependencies import SESSION_COOKIE, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserOut

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_DAYS * 24 * 60 * 60,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Email/password login. Returns the user and sets a session cookie."""
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    # Email comparison is case-insensitive; store as-typed but match lower.
    if not user:
        # Fall back to as-typed match in case the DB has mixed case.
        user = await db.scalar(select(User).where(User.email == payload.email))

    if (
        not user
        or not user.hashed_password
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    token = create_access_token(user.id)
    _set_session_cookie(response, token)
    return LoginResponse(user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    _clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# Google OAuth scaffolds — return informative responses until wired.
# ---------------------------------------------------------------------------


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    if not is_google_configured():
        # Surface a clear error in the dev UI rather than a 500.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured. Set TASKS_GOOGLE_CLIENT_ID and "
            "TASKS_GOOGLE_CLIENT_SECRET, then restart.",
        )
    # TODO(mark): build authlib client and redirect to Google consent screen.
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Google OAuth login flow not yet implemented.",
    )


@router.get("/google/callback")
async def google_callback() -> RedirectResponse:
    if not is_google_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured.",
        )
    # TODO(mark): exchange code, upsert user, set session cookie, redirect to /.
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Google OAuth callback not yet implemented.",
    )


@router.get("/google/status")
async def google_status() -> dict[str, bool]:
    """Surfaces whether Google login is currently usable. Used by the UI to
    enable/disable the SSO button without a network round-trip to Google."""
    return {"configured": is_google_configured()}

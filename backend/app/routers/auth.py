"""Authentication routes — login, logout, me, Google OAuth."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.oauth import is_google_configured, oauth_client
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.dependencies import SESSION_COOKIE, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserOut

logger = logging.getLogger("tasks.auth")

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
async def google_login(request: Request):
    """Redirect the browser to Google's OAuth consent screen."""
    oauth = oauth_client()
    if oauth is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured. Set TASKS_GOOGLE_CLIENT_ID and "
            "TASKS_GOOGLE_CLIENT_SECRET, then restart.",
        )
    # Prefer the explicit env-configured redirect URI. If unset, fall back
    # to deriving one from the current request — useful in dev when the
    # user hasn't filled in TASKS_GOOGLE_REDIRECT_URI.
    redirect_uri = settings.GOOGLE_REDIRECT_URI or str(
        request.url_for("google_callback")
    )
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange the authorization code, upsert the user, set session cookie."""
    oauth = oauth_client()
    if oauth is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured.",
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001 — Authlib raises various subclasses
        logger.warning("Google OAuth code exchange failed: %s", exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Google OAuth exchange failed"
        ) from exc

    userinfo = token.get("userinfo")
    if not userinfo:
        # Older flows: hit the userinfo endpoint explicitly.
        userinfo = (await oauth.google.userinfo(token=token)) or {}

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not sub or not email:
        logger.warning("Google userinfo missing sub or email: %s", userinfo)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google did not return an email; cannot sign in.",
        )

    # Upsert: prefer match-by-google_sub; fall back to match-by-email
    # (covers the case where the user was first created via password and
    # is now linking Google for the first time).
    user = await db.scalar(select(User).where(User.google_sub == sub))
    if not user:
        user = await db.scalar(select(User).where(User.email == email))

    if user is None:
        user = User(
            email=email,
            google_sub=sub,
            display_name=userinfo.get("name"),
        )
        db.add(user)
    else:
        if not user.google_sub:
            user.google_sub = sub
        if not user.display_name and userinfo.get("name"):
            user.display_name = userinfo["name"]

    await db.flush()
    await db.refresh(user)

    # Issue a session cookie, then bounce to the SPA root.
    session_token = create_access_token(user.id)
    redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_DAYS * 24 * 60 * 60,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    return redirect


@router.get("/google/status")
async def google_status() -> dict[str, bool]:
    """Surfaces whether Google login is currently usable. Used by the UI to
    enable/disable the SSO button without a network round-trip to Google."""
    return {"configured": is_google_configured()}

"""Public demo mode (TASKS_DEMO_MODE=true): tasks-demo.markcheli.com.

The demo is its own deployment with its own database holding only the Claudius Banks seed
(app/services/demo_seed.py), rebuilt nightly. Anyone may look; nobody may change anything.
Three layers keep it that way:

1. `DemoReadOnlyMiddleware` refuses every POST/PUT/PATCH/DELETE except `ALLOWED_WRITES`
   (signing in as the persona and signing out). A new route is refused without anyone
   remembering to list it.
2. Request sessions run in READ ONLY transactions (`get_db` → `make_read_only`), so a write
   that slipped past the middleware still fails in Postgres.
3. Startup refuses Google and password-login settings (`check_demo_settings`) and any database
   holding a user who is not a demo persona (`check_demo_database`), so the demo can never be
   pointed at real data.
"""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEMO_EMAIL_DOMAIN = "@tasks.dev"
READ_ONLY_DETAIL = "This is the public demo with made-up data, so nothing can be changed or saved."

# Full paths. Everything else that writes is refused.
ALLOWED_WRITES = [
    re.compile(r"^/api/auth/(demo|logout)$"),
]


def write_allowed(method: str, path: str) -> bool:
    if method.upper() in SAFE_METHODS:
        return True
    return any(p.match(path) for p in ALLOWED_WRITES)


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.DEMO_MODE and not write_allowed(request.method, request.url.path):
            return JSONResponse({"detail": READ_ONLY_DETAIL, "demo": True}, status_code=403)
        return await call_next(request)


class NoIndexMiddleware(BaseHTTPMiddleware):
    """The demo is linked from the owner's site but should not be indexed as if it were a product."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if settings.DEMO_MODE:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response


async def make_read_only(db: AsyncSession) -> None:
    """Start the session's transaction as READ ONLY. Must run before any other statement."""
    await db.execute(text("SET TRANSACTION READ ONLY"))


def check_demo_settings() -> None:
    if settings.GOOGLE_CLIENT_ID or settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "FATAL: demo mode must not have Google SSO configured (TASKS_GOOGLE_*); "
            "visitors sign in as the demo persona."
        )
    if settings.TEST_USER_EMAIL or settings.TEST_USER_PASSWORD:
        raise RuntimeError(
            "FATAL: demo mode must not have a password user (TASKS_TEST_USER_*); "
            "visitors sign in as the demo persona."
        )
    if not settings.DEMO_USER_EMAIL.endswith(DEMO_EMAIL_DOMAIN):
        raise RuntimeError(f"FATAL: TASKS_DEMO_USER_EMAIL must be a {DEMO_EMAIL_DOMAIN} persona.")


async def check_demo_database(db: AsyncSession) -> None:
    """Refuse to serve (or reseed) a database that holds anyone but demo personas."""
    from app.models.user import User

    real = await db.scalar(select(User.id).where(~User.email.endswith(DEMO_EMAIL_DOMAIN)).limit(1))
    if real is not None:
        raise RuntimeError(
            "FATAL: demo mode is pointed at a database with real users. "
            "The demo must run on its own database holding only the seed."
        )

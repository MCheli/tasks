"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import check_production_settings, settings
from app.core.headers import SecurityHeadersMiddleware
from app.db.session import engine
from app.demo import DemoReadOnlyMiddleware, NoIndexMiddleware
from app.routers import health

logger = logging.getLogger("tasks")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


async def _check_demo() -> None:
    """Demo mode fails closed: wrong settings or a database with real users stop startup."""
    from app.db.session import AsyncSessionLocal
    from app.demo import check_demo_database, check_demo_settings

    check_demo_settings()
    async with AsyncSessionLocal() as db:
        await check_demo_database(db)
    logger.info("Demo mode: read-only, signed-in visitors see %s.", settings.DEMO_USER_EMAIL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    errors, warnings = check_production_settings(settings)
    for warning in warnings:
        logger.warning("Insecure production setting: %s", warning)
    if errors:  # fail closed: refuse to serve with public secrets
        for error in errors:
            logger.error("INSECURE PRODUCTION SETTING: %s", error)
        raise RuntimeError("FATAL: insecure production settings: " + " ".join(errors))
    if settings.DEMO_MODE:
        await _check_demo()  # raises → the server refuses to start

    # Startup: seed test user (only does work if TASKS_TEST_USER_EMAIL/PASSWORD set
    # AND the User model exists yet). Imported lazily so Phase 0 boots without models.
    try:
        from app.services.seed import ensure_test_user  # noqa: WPS433

        await ensure_test_user()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Seed step skipped: %s", exc)
    yield
    await engine.dispose()


app = FastAPI(
    title="Tasks",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authlib stores OAuth state across the Google round-trip in this signed
# cookie. Use a name distinct from our JWT session cookie ('session') so
# Starlette doesn't overwrite the JWT when it serializes the (empty)
# OAuth-state session at end-of-request.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET,
    session_cookie="tasks_oauth_state",
    https_only=settings.COOKIE_SECURE,
    same_site="lax",
)


# Public demo: refuse writes, keep it out of search engines. Both are no-ops unless
# TASKS_DEMO_MODE is set (see app/demo.py).
app.add_middleware(DemoReadOnlyMiddleware)
app.add_middleware(NoIndexMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def _unhandled(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# API routes — mounted under /api
app.include_router(health.router, prefix="/api", tags=["health"])

# Auth, cycles, tasks routers loaded lazily when their modules exist.
try:
    from app.routers import auth as _auth_router  # noqa: WPS433

    app.include_router(_auth_router.router, prefix="/api/auth", tags=["auth"])
except Exception as _exc:  # noqa: BLE001  -- catch ImportError AND submodule errors
    logger.warning("Auth router not loaded: %s", _exc)

try:
    from app.routers import cycles as _cycles_router  # noqa: WPS433

    app.include_router(_cycles_router.router, prefix="/api/cycles", tags=["cycles"])
except Exception as _exc:  # noqa: BLE001  -- catch ImportError AND submodule errors
    logger.info("Cycles router not loaded: %s", _exc)

try:
    from app.routers import tasks as _tasks_router  # noqa: WPS433

    app.include_router(_tasks_router.router, prefix="/api/tasks", tags=["tasks"])
except Exception as _exc:  # noqa: BLE001  -- catch ImportError AND submodule errors
    logger.info("Tasks router not loaded: %s", _exc)

try:
    from app.routers import history as _history_router  # noqa: WPS433

    app.include_router(_history_router.router, prefix="/api/history", tags=["history"])
except Exception as _exc:  # noqa: BLE001  -- catch ImportError AND submodule errors
    logger.info("History router not loaded: %s", _exc)

try:
    from app.routers import api_keys as _api_keys_router  # noqa: WPS433

    app.include_router(_api_keys_router.router, prefix="/api/api-keys", tags=["api-keys"])
except Exception as _exc:  # noqa: BLE001  -- catch ImportError AND submodule errors
    logger.info("API keys router not loaded: %s", _exc)


# Static frontend (production build copied to /app/static by Dockerfile).
# Path is configurable via TASKS_STATIC_DIR for dev experimentation.
STATIC_DIR = Path(os.environ.get("TASKS_STATIC_DIR", "/app/static"))


def static_file(static_dir: Path, full_path: str) -> Path | None:
    """Return the file under static_dir that full_path names, or None.

    The path arrives percent-decoded, so "..%2f" must not be allowed to escape the directory.
    """
    root = static_dir.resolve()
    try:
        candidate = (root / full_path).resolve()
    except (OSError, ValueError):  # e.g. an embedded NUL byte
        return None
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return None


if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Don't intercept API paths (FastAPI handles those before this catch-all).
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        # Serve a file directly if it exists in static (favicon, etc.), else index.html.
        candidate = static_file(STATIC_DIR, full_path)
        if candidate:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")

else:
    logger.info("Static dir %s missing or empty; SPA not mounted (dev mode).", STATIC_DIR)

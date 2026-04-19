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

from app.config import settings
from app.db.session import engine
from app.routers import health

logger = logging.getLogger("tasks")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    docs_url="/api/docs" if settings.ENABLE_DOCS else None,
    openapi_url="/api/openapi.json" if settings.ENABLE_DOCS else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# Static frontend (production build copied to /app/static by Dockerfile).
# Path is configurable via TASKS_STATIC_DIR for dev experimentation.
STATIC_DIR = Path(os.environ.get("TASKS_STATIC_DIR", "/app/static"))

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
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")

else:
    logger.info("Static dir %s missing or empty; SPA not mounted (dev mode).", STATIC_DIR)

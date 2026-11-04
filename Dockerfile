# syntax=docker/dockerfile:1.7

# ---- Stage 1: Build the Vue frontend ----
FROM node:24.22.1-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python deps (build toolchain lives here only) ----
FROM python:3.11.18-slim AS python-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt is the pinned lockfile, so a rebuild never pulls new library versions.
# setuptools is bumped because the base's copy vendors vulnerable wheel/jaraco.context.
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install pip==26.3 setuptools==84.2.1 \
    && /opt/venv/bin/pip install -r /tmp/requirements.txt

# ---- Stage 3: Backend runtime (no compiler, no curl) ----
FROM python:3.11.18-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH

# `upgrade` takes Debian security fixes newer than the base tag. libpq5 is the runtime
# half of libpq-dev; the system pip/setuptools/wheel get the same bump as the venv.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pip==26.3 setuptools==84.2.1 wheel==0.48.0

COPY --from=python-deps /opt/venv /opt/venv

# Non-root user (uid 1000 — matches DEPLOYMENT_HANDOFF_TEMPLATE).
RUN useradd --uid 1000 --create-home --shell /bin/bash app

WORKDIR /app

# Backend code (the app, alembic config, alembic env)
COPY backend/ ./backend/

# Built frontend → /app/static (where main.py expects it)
COPY --from=frontend-build /app/frontend/dist ./static/

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R app:app /app

USER app
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).read()"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# syntax=docker/dockerfile:1.7

# ---- Stage 1: Build the Vue frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Backend runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for asyncpg, bcrypt, healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (uid 1000 — matches DEPLOYMENT_HANDOFF_TEMPLATE).
RUN useradd --uid 1000 --create-home --shell /bin/bash app

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

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
  CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

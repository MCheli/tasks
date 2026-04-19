# Deployment

Single Docker container that runs the FastAPI backend and serves the built Vue frontend as static files. PostgreSQL runs as a separate service (separate container in dev, managed by the deployment agent in prod).

## Target Architecture

```
┌────────────────────────────────────────────────────────┐
│  Mark's home server (Dell R630, Ubuntu 24.04)         │
│                                                        │
│  ┌──────────────┐   ┌────────────────────────────┐   │
│  │  NGINX       │──▶│  cycle-todo container      │   │
│  │  (managed by │   │  (FastAPI + static Vue)    │   │
│  │  deployment  │   │  Port 8000 internal         │   │
│  │  agent)      │   └────────────────────────────┘   │
│  │              │            │                        │
│  │  tasks.      │            ▼                        │
│  │  markcheli.  │   ┌────────────────────────────┐   │
│  │  com (HTTPS) │   │  postgres:15 container     │   │
│  └──────────────┘   │  (managed by deployment)   │   │
│                     └────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

Production image: `ghcr.io/mcheli/cycle-todo:latest` (and `:${SHA}` for specific versions).

## Dockerfile (multi-stage)

```dockerfile
# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Outputs to /app/frontend/dist

# ---- Stage 2: Backend with static files ----
FROM python:3.11-slim AS runtime

# System deps for asyncpg, bcrypt, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/

# Copy built frontend from stage 1 into a location FastAPI serves
COPY --from=frontend-build /app/frontend/dist ./static/

# Entrypoint: run migrations then start server
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### `docker/entrypoint.sh`

```bash
#!/bin/sh
set -e

# Wait for DB (simple poll)
echo "Waiting for database..."
until python -c "import asyncio, asyncpg, os; asyncio.run(asyncpg.connect(os.environ['DATABASE_URL'].replace('postgresql+asyncpg','postgresql')).close())" 2>/dev/null; do
  sleep 1
done
echo "Database ready."

# Run migrations
cd /app
alembic upgrade head

# Start app
exec "$@"
```

## `docker-compose.yml` (local dev)

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: cycle_todo
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: cycle_todo
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cycle_todo"]
      interval: 5s

  db-test:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: cycle_todo_test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data  # ephemeral; wiped on restart

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://cycle_todo:changeme@db:5432/cycle_todo
      JWT_SECRET: ${JWT_SECRET:-dev-only-not-secret}
      TEST_USER_EMAIL: ${TEST_USER_EMAIL}
      TEST_USER_PASSWORD: ${TEST_USER_PASSWORD}
      ENV: development
      COOKIE_SECURE: "false"
      ALLOWED_ORIGINS: "http://localhost:5173,http://localhost:8000"
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app/backend  # hot-reload in dev (bind mount)

volumes:
  pg_data:
```

## `.env.example`

```dotenv
# Runtime environment
ENV=development
ENABLE_DOCS=true

# Database connection
DATABASE_URL=postgresql+asyncpg://cycle_todo:changeme@localhost:5432/cycle_todo

# JWT / session
JWT_SECRET=CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7
COOKIE_SECURE=false
COOKIE_DOMAIN=

# Test user (seeded on startup if set)
TEST_USER_EMAIL=
TEST_USER_PASSWORD=

# Google OAuth (leave blank until Mark sets up Google Cloud Console)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

# CORS (comma-separated)
ALLOWED_ORIGINS=http://localhost:5173
```

## GitHub Actions: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: cycle_todo_test
        ports: ['5433:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: |
          cd backend
          pip install -r requirements.txt
      - name: Lint
        run: |
          cd backend
          ruff check .
          black --check .
      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5433/cycle_todo_test
          JWT_SECRET: test-secret-key
        run: |
          cd backend
          pytest --cov=app --cov-report=term-missing

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run build

  e2e:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - name: Build and run app
        run: |
          docker compose up -d
          # wait for healthcheck
          timeout 60 sh -c 'until curl -fsS http://localhost:8000/api/health; do sleep 2; done'
      - name: Install Playwright
        run: |
          cd e2e
          npm ci
          npx playwright install --with-deps chromium
      - name: Run E2E
        env:
          TEST_USER_EMAIL: ${{ secrets.TEST_USER_EMAIL }}
          TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}
          BASE_URL: http://localhost:8000
        run: cd e2e && npm test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: e2e/playwright-report/
```

## GitHub Actions: `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha,prefix=
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Local Development

1. Copy `.env.example` to `.env` and fill in values.
2. Generate a JWT secret: `openssl rand -hex 32` → paste into `JWT_SECRET`.
3. Set `TEST_USER_EMAIL` and `TEST_USER_PASSWORD` from `~/repos/tallied/.env` (same Claudius credentials).
4. `docker compose up -d db db-test` to start Postgres.
5. `cd backend && alembic upgrade head` to create tables.
6. `cd backend && uvicorn app.main:app --reload --port 8000` for the API.
7. `cd frontend && npm install && npm run dev` for Vite on 5173.
8. Visit `http://localhost:5173`. Log in with the test user.

## Running the Container Locally

```bash
docker compose up --build
# Visit http://localhost:8000 — the container serves both API and frontend.
```

## Production Deployment

*The deployment agent handles the actual deployment. This section describes what the deployment agent needs to do.*

### What the Deployment Agent Will Need

1. **Image:** `ghcr.io/mcheli/cycle-todo:latest` (pull on deploy).
2. **PostgreSQL 15** instance, reachable from the container. Create a database and user dedicated to this app.
3. **Environment variables** (see section below).
4. **Persistent storage:** none required on the app container (all state is in Postgres).
5. **NGINX reverse proxy:** `tasks.markcheli.com` → container port 8000. HTTPS termination at NGINX with Let's Encrypt or Cloudflare Origin Cert.
6. **Health check:** `GET /api/health` returns 200. Use for container orchestration health probes.

### Required Production Environment Variables

| Variable | Example | Notes |
|---|---|---|
| `ENV` | `production` | |
| `ENABLE_DOCS` | `false` | Hide `/api/docs` in prod |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@db-host:5432/cycle_todo` | Use a dedicated DB |
| `JWT_SECRET` | 64-char random hex | Generate via `openssl rand -hex 32` |
| `JWT_EXPIRE_DAYS` | `7` | |
| `COOKIE_SECURE` | `true` | Required for HTTPS |
| `COOKIE_DOMAIN` | `.markcheli.com` | Optional; allows sharing between subdomains if needed |
| `TEST_USER_EMAIL` | `claudius@markcheli.com` | Seeds the test user. Set to same as dev for now. |
| `TEST_USER_PASSWORD` | `<same as dev>` | |
| `GOOGLE_CLIENT_ID` | `...apps.googleusercontent.com` | From Google Cloud Console OAuth credentials |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-...` | |
| `GOOGLE_REDIRECT_URI` | `https://tasks.markcheli.com/api/auth/google/callback` | |
| `ALLOWED_ORIGINS` | `https://tasks.markcheli.com` | |

### Database Migrations

The container entrypoint runs `alembic upgrade head` on every startup. Safe to run repeatedly; no-op if schema is already current.

For manual migration (e.g., before a risky deploy):
```bash
docker run --rm --env-file prod.env ghcr.io/mcheli/cycle-todo:latest \
  alembic upgrade head
```

### Zero-Downtime Deploys

Not required for v1 (single-user app, brief downtime is fine). If ever needed: run two containers behind NGINX and flip them. Alembic migrations are additive in practice.

### Backups

Out of scope for this repo. Deployment agent is responsible for scheduling `pg_dump` to the NAS.

### Google OAuth Setup (Mark does this himself)

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project, "Cycle Todo."
3. APIs & Services → OAuth consent screen: External, add Mark's email as test user.
4. APIs & Services → Credentials → Create OAuth 2.0 Client ID.
   - Type: Web application.
   - Authorized redirect URIs: `https://tasks.markcheli.com/api/auth/google/callback` and `http://localhost:8000/api/auth/google/callback` for local testing.
5. Copy Client ID and Client Secret into production env vars.

### Rollback

```bash
# Retag the previous SHA as latest and redeploy
docker pull ghcr.io/mcheli/cycle-todo:<previous-sha>
# deployment agent swaps the running image
```

Or pin deployments to specific SHAs and roll forward/backward by changing the tag.

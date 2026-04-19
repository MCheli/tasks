# Architecture

## Overview

A single-container, self-hosted web application. The FastAPI backend serves both the REST API under `/api/*` and the built Vue 3 frontend as static files at `/`. PostgreSQL runs as a separate container in development and as a separate service (managed by the deployment agent) in production.

## Design Principles

- **User-scoped isolation.** Every query filters by `user_id`. No cross-user reads, ever. Enforce at the dependency layer.
- **Calculate, don't store.** Push-forward counts, cycle summary counts, and any aggregates are computed on read from source tables. Never cache them in columns.
- **Soft delete only.** `deleted_at IS NULL` is the implicit filter on every task query. Add a helper to enforce this.
- **Persistent task identity.** A task's identity is `persistent_task_id` (UUID). Its *row* in any given cycle is just a snapshot with a status and position.
- **Minimal schema.** Five tables: `users`, `cycles`, `tasks`, `display_id_sequences`, and (optional) `alembic_version`. That's it.
- **Stateless API, JWT in httpOnly cookie.** No server-side sessions. JWT contains user_id. Cookies scoped to the domain.

## Tech Stack

| Layer | Tech | Version |
|---|---|---|
| Backend framework | FastAPI | >=0.110 |
| ASGI server | Uvicorn | >=0.27 |
| ORM | SQLAlchemy | 2.0+ (async) |
| Migrations | Alembic | >=1.13 |
| Validation | Pydantic | 2.x |
| DB | PostgreSQL | 15 |
| Python | CPython | 3.11+ |
| Frontend | Vue | 3.4+ |
| Frontend build | Vite | 5.x |
| Styling | Tailwind CSS | 3.4+ |
| State | Pinia | 2.x |
| Router | Vue Router | 4.x |
| HTTP | Axios | 1.6+ |
| Lint (py) | ruff + black | latest |
| Lint (js) | ESLint + Prettier | latest |
| Test (py) | pytest, pytest-asyncio, httpx | latest |
| Test (e2e) | Playwright MCP | (via Claude Code) |
| Container | Docker | multi-stage |
| CI | GitHub Actions | — |
| Registry | GHCR | — |

## Project Structure

```
cycle-todo/
├── README.md
├── AGENT_INSTRUCTIONS.md        (from this doc set — kept for agent reference)
├── ARCHITECTURE.md              (from this doc set)
├── DATABASE_SCHEMA.md
├── API_SPEC.md
├── UI_FLOWS.md
├── BACKEND_IMPLEMENTATION.md
├── FRONTEND_IMPLEMENTATION.md
├── TESTING_STRATEGY.md
├── DEPLOYMENT.md                (agent fills in during build)
├── DECISIONS.md                 (agent creates and updates when making judgment calls)
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile                   (multi-stage)
├── docker-compose.yml           (local dev)
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              (FastAPI app, static file mount, startup events)
│   │   ├── config.py            (pydantic-settings, reads .env)
│   │   ├── dependencies.py      (get_db, get_current_user)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── security.py      (password hashing, JWT encode/decode)
│   │   │   └── oauth.py         (Google OAuth stubs)
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py          (Base = declarative_base())
│   │   │   └── session.py       (async engine, SessionLocal)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── cycle.py
│   │   │   └── task.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── cycle.py
│   │   │   └── task.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── cycles.py
│   │   │   ├── tasks.py
│   │   │   └── health.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── cycle_service.py
│   │       ├── task_service.py
│   │       └── display_id_service.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── fixtures/
│       │   └── factories.py
│       ├── unit/
│       │   ├── test_cycle_service.py
│       │   ├── test_task_service.py
│       │   └── test_display_id.py
│       └── api/
│           ├── test_auth.py
│           ├── test_cycles.py
│           └── test_tasks.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   ├── router/
│   │   │   └── index.js
│   │   ├── stores/
│   │   │   ├── auth.js
│   │   │   ├── cycles.js
│   │   │   └── tasks.js
│   │   ├── api/
│   │   │   ├── client.js        (axios instance + interceptors)
│   │   │   ├── auth.js
│   │   │   ├── cycles.js
│   │   │   └── tasks.js
│   │   ├── views/
│   │   │   ├── LoginView.vue
│   │   │   ├── CycleView.vue    (main task list)
│   │   │   ├── TransitionView.vue
│   │   │   └── HistoryView.vue
│   │   ├── components/
│   │   │   ├── TaskItem.vue
│   │   │   ├── TaskInput.vue
│   │   │   ├── TabSwitcher.vue
│   │   │   ├── TransitionSummary.vue
│   │   │   ├── GanttChart.vue
│   │   │   └── ...
│   │   ├── composables/
│   │   │   ├── useDragReorder.js
│   │   │   └── useKeyboardShortcuts.js
│   │   └── assets/
│   │       └── main.css         (Tailwind entrypoint)
│   └── tests/
│       └── (vitest unit tests for composables and stores, optional)
└── docs/
    └── screenshots/             (agent saves Playwright screenshots here)
```

## Request Flow

```
Browser
   │
   ├── GET /         → FastAPI StaticFiles → index.html (Vue SPA)
   ├── GET /assets/* → FastAPI StaticFiles → JS/CSS bundles
   │
   └── /api/*
         ↓
       FastAPI router
         ↓
       Auth dependency (decodes JWT cookie, loads User)
         ↓
       Service layer (business logic, transactions)
         ↓
       SQLAlchemy async session → PostgreSQL
```

## Auth Model

- **Login:** `POST /api/auth/login` with `{email, password}` → returns 200 and sets `session` httpOnly cookie with JWT.
- **Logout:** `POST /api/auth/logout` → clears the cookie.
- **Me:** `GET /api/auth/me` → current user.
- **Google OAuth:** `/api/auth/google/login` → redirects to Google. `/api/auth/google/callback` → exchanges code, creates/finds user, sets cookie. *Wired but not configured; awaits Mark's Google Cloud setup.*
- **JWT contents:** `{sub: user_id, exp: now+7d, iat: now}`. HS256 signed with `JWT_SECRET`.
- **Dependency:** `get_current_user` reads the cookie, decodes, loads the user from DB, raises 401 if any step fails.

## Data Scoping

Every request that touches user data MUST pass through `get_current_user`, and every query MUST filter by `user_id`. Enforce this in the service layer, not the router. A helper:

```python
def scope_to_user(query, user_id):
    return query.where(Model.user_id == user_id)
```

Tests for cross-user isolation are mandatory.

## Frontend Static Serving

Production build: `npm run build` emits to `frontend/dist/`. The multi-stage Dockerfile copies `dist/` into `/app/static/` in the backend image. `main.py` mounts it:

```python
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

Catch-all SPA routing: any GET to a non-`/api` path returns `index.html` so Vue Router can handle client-side routing.

Dev mode: `npm run dev` runs Vite on port 5173, proxying `/api` to the FastAPI backend on port 8000.

## Environment Variables

See `.env.example` for the full list. All config flows through `app/config.py` via `pydantic-settings`. No hardcoded secrets anywhere.

## Out of Scope

- No Redis. No Celery. No message queue. This is a single-user todo app.
- No background jobs. Everything is synchronous request/response.
- No file uploads. Task notes are text only.
- No offline mode / PWA service worker in v1 (possible future).

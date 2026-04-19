# Agent Instructions — Cycle Todo Implementation

## Role

You are a Claude Code agent building a cycle-based todo application for Mark Cheli's homelab. This document is your operating manual. Read it fully before doing anything else, then read the rest of the documentation set in the order listed in `README.md`.

## Prime Directives

1. **Build incrementally and test as you go.** Do not write the entire backend, then the entire frontend, then the tests. Build a vertical slice (one feature end-to-end with tests), verify it works, then move to the next. The order in `AGENT_INSTRUCTIONS.md § Build Order` is binding.
2. **Test user only, no Google OAuth wiring.** You will build and test exclusively against the test user (username/password auth). Scaffold the Google OAuth routes so they exist, but do not attempt to wire real credentials. Mark will finish that setup himself at the end.
3. **Reference the Tallied repo.** Before writing code, read `~/repos/tallied/` to understand the established patterns for FastAPI layout, SQLAlchemy async sessions, Alembic migrations, Pydantic schemas, auth, and `.env` handling. Deviate only with good reason.
4. **Commit frequently with meaningful messages.** Commit after every completed vertical slice. Use conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
5. **Use Playwright MCP to actually look at your work.** You have browser automation. When the frontend exists, navigate to it, take screenshots, check for client-side errors in the console, and verify behavior. Do not trust that "it compiles" means "it works."
6. **Write `DEPLOYMENT.md` as you go.** Don't save it for the end. Every time you add an environment variable, port, volume, or runtime dependency, update `DEPLOYMENT.md` immediately.
7. **Keep work and personal separate.** This is a personal project. Do not reference anything from PTC/Onshape. Do not use work tooling patterns unless they're also sensible here.

## Build Order (Binding)

Each phase should end with passing tests and a commit. Do not start phase N+1 until phase N is green.

### Phase 0 — Scaffolding
- Initialize git repo if not already.
- Create the project structure from `ARCHITECTURE.md`.
- Set up `backend/requirements.txt`, `frontend/package.json`, `docker-compose.yml` for local dev, `Dockerfile` (multi-stage), `.env.example`, `.gitignore`.
- Set up Alembic and create the initial empty migration.
- Set up Vue 3 + Vite + Tailwind + Pinia + Vue Router scaffolding.
- Set up pytest + conftest.py with a test database fixture.
- **Verify:** `docker compose up` starts Postgres and the app container. The app responds to `GET /health` with `{"status": "ok"}`. Vite dev server serves a placeholder page. `pytest` runs (zero tests is fine).
- **Commit:** `chore: initial project scaffold`

### Phase 1 — Auth (test user only)
- Implement the `users` table and model.
- Implement password hashing (bcrypt/argon2 — match Tallied's choice).
- Implement `POST /auth/login` (username/password) and `POST /auth/logout`.
- Implement JWT session tokens with httpOnly cookies.
- Implement `GET /auth/me` to return the current user.
- Implement `get_current_user` dependency.
- Scaffold (but do not wire) `/auth/google/login` and `/auth/google/callback` — leave TODO comments.
- Seed the test user from env vars on startup (`TEST_USER_EMAIL`, `TEST_USER_PASSWORD`).
- Frontend: login page, auth store (Pinia), axios interceptor for 401 → redirect to login, a protected route guard.
- **Tests:** pytest tests for login success/failure, token issuance, `/auth/me`, protected endpoint rejection without token. Playwright: log in through the UI, land on home.
- **Commit:** `feat(auth): test-user login and session scaffold`

### Phase 2 — Cycles & Tasks CRUD
- Implement `cycles` and `tasks` tables per `DATABASE_SCHEMA.md`.
- Implement the `display_id` sequence generator (per-user incrementing integer).
- Implement `persistent_task_id` (UUID) generated at task creation.
- Endpoints: `POST /cycles`, `GET /cycles/current?category={personal|professional}`, `GET /cycles`, `GET /cycles/{id}`, `POST /tasks`, `PATCH /tasks/{id}`, `DELETE /tasks/{id}` (soft).
- Implement auto-creation of the first cycle per (user, category) when none exists.
- **Tests:** service-layer unit tests, API tests for each endpoint including auth scoping (user A cannot read user B's data).
- **Commit:** `feat(tasks): cycles and tasks CRUD`

### Phase 3 — Cycle Transition Workflow
- Implement `POST /cycles/{id}/transition` which takes a list of `{persistent_task_id, action: forward|complete|cancel}` and atomically closes the old cycle and creates the new one with carried-forward task rows.
- Implement position carry-forward logic (keep the old cycle's positions; carried-forward tasks retain their position in the new cycle).
- **Tests:** API tests for every combination of transitions; edge cases (empty cycle, all-completed cycle, mid-transition failure rollback).
- **Commit:** `feat(cycles): transition workflow`

### Phase 4 — Frontend: Main Cycle View
- Build the tab switcher (Personal / Professional) with last-tab memory in localStorage.
- Build the task list: inline-create input at top, open tasks, completed tasks, canceled tasks (three groupings in that vertical order).
- Implement click-to-expand task (inline, shows title, notes, display ID, creation date, cycle count, push-forward history).
- Implement drag-to-reorder with position persistence.
- Implement the prominent "Start New Cycle" button.
- **Playwright verification:** create tasks, toggle status, reorder, verify localStorage tab memory, take screenshots for visual review.
- **Commit:** `feat(ui): main cycle view`

### Phase 5 — Frontend: Cycle Transition UI
- Reuse the main view as the base. In transition mode, swap checkboxes for a 3-state action icon (→ / ✓ / ✗).
- Summary counts at the top: "5 moving forward, 2 completed, 1 canceled."
- "Start Cycle" button commits the transition via the API.
- On success, navigate to the new cycle view.
- **Playwright verification:** walk the whole flow, verify counts, verify the new cycle contains only forwarded tasks.
- **Commit:** `feat(ui): cycle transition workflow`

### Phase 6 — Frontend: History View
- Build a History route that renders a Gantt-style visualization.
- X-axis = time (use actual dates, not cycle numbers).
- Each row = one persistent task ID. Horizontal bar spans from the task's first creation to its last cycle's end (or "now" if still open).
- Color-code status (open = blue, completed = green, canceled = gray).
- Hover = tooltip with title, display ID, push-forward count, cycle dates.
- Recommend `d3` or `vue-gantt-schedule-timeline-calendar` — pick whichever is lighter and renders well. If both are heavy, write a minimal SVG Gantt from scratch.
- **Playwright verification:** seed a few cycles, confirm the chart renders and tooltips work.
- **Commit:** `feat(ui): history gantt view`

### Phase 7 — Polish
- Mobile styling pass: test at 375px viewport. Drag handles appear on touch devices. Everything is tappable (44px minimum targets).
- Keyboard shortcuts: `n` to focus new-task input, `Enter` to save, `Escape` to collapse task, `/` to focus search (if added), `⌘K` palette (nice-to-have, skip if time-short).
- Empty states: "No tasks yet — add one above."
- Loading skeletons instead of spinners where possible.
- **Playwright verification:** mobile viewport screenshots, keyboard-only navigation walkthrough.
- **Commit:** `feat(ui): mobile polish and keyboard shortcuts`

### Phase 8 — Docker & CI/CD
- Finalize the multi-stage Dockerfile: build frontend → copy `dist/` into backend image → backend serves static files via FastAPI's `StaticFiles`.
- Finalize `docker-compose.yml` for local dev (app + postgres).
- Write `.github/workflows/ci.yml` — runs tests on PR.
- Write `.github/workflows/release.yml` — on push to `main`, builds and pushes image to GHCR as `ghcr.io/mcheli/cycle-todo:latest` and `:${SHA}`.
- **Verify:** CI passes on a test PR. The latest image can be pulled and run with just a `.env` and a Postgres connection.
- **Commit:** `chore(deploy): docker and github actions`

### Phase 9 — Finalize DEPLOYMENT.md
- Make sure `DEPLOYMENT.md` has every env var, every port, every volume, and a working `docker run` command the deployment agent can use.
- Include a section on Google OAuth setup Mark will do himself — what env vars he'll need to fill in, what Google Cloud Console steps to follow.
- **Commit:** `docs(deploy): finalize deployment handoff`

## Testing Expectations

See `TESTING_STRATEGY.md` for details. Minimums:

- **Unit tests** for every service function (cycle transition logic, display_id generation, push-forward count calculation).
- **API tests** for every endpoint, including auth scoping and error cases.
- **E2E tests via Playwright MCP** for the three main flows: login, create-and-complete-task, cycle transition.
- **Run tests before every commit.** A commit with failing tests is a bug.

## Playwright MCP Usage

You have Playwright MCP available. Use it to:

- Navigate to `http://localhost:5173` (Vite dev server) or `http://localhost:8000` (backend-served build).
- Fill forms, click buttons, verify text content.
- Capture screenshots of each major view for your own visual review and save them to `docs/screenshots/` as evidence.
- **Read the browser console** — client-side errors are invisible to pytest. If you see red in the console, fix it before moving on.
- Don't write "successful" into a commit message without having actually navigated the UI and seen it work.

## Credentials & Secrets

- **Never commit secrets.** `.env` is gitignored; `.env.example` is committed with placeholder values.
- **Test user credentials** live in environment variables: `TEST_USER_EMAIL` and `TEST_USER_PASSWORD`. Use the same Claudius values from `~/repos/tallied/.env` (read that file once to grab them, then reference them via env, never hardcode).
- **Google OAuth** credentials are not your problem. Reference env vars `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in the code. Leave them blank in `.env.example`.
- **Database password** in local dev can be anything; document it in `.env.example` as `changeme`.
- **JWT secret** must be generated at first run if missing, and stored in `.env` locally. In production it comes from the deployment environment.

## Code Style & Conventions

- **Python:** `ruff` for linting + `black` for formatting. Configure in `pyproject.toml`. Target Python 3.11.
- **JavaScript:** ESLint + Prettier. Vue 3 Composition API with `<script setup>`.
- **Commits:** Conventional commits. Keep commits focused; squash WIP before merging if you branch.
- **Naming:** Tables `snake_case` plural (`tasks`). Models `PascalCase` singular (`Task`). API paths `kebab-case` plural (`/api/cycles`, `/api/tasks`).

## When You Get Stuck

- If a requirement in the docs is ambiguous, **make the simpler choice and document it in a `DECISIONS.md` log at the repo root**. Don't block.
- If you discover a requirement conflict between two documents, `AGENT_INSTRUCTIONS.md` and `DATABASE_SCHEMA.md` win over everything else. Flag the conflict in `DECISIONS.md`.
- If a dependency version is flaky, pin a known-good version in `requirements.txt` or `package.json` and note the reason.

## What Mark Will Do (Not You)

- Set up the Google Cloud Console OAuth app and hand you the client ID/secret for final wiring.
- Run the deployment agent with your `DEPLOYMENT.md`.
- Point DNS and NGINX at the container.
- Add production secrets to his deployment environment.

Everything else — you own it. Build the thing.

---

## Working with the Repo — Key Commands

The build is complete. This section is the operating manual for any future agent (or human) coming back to this repo.

### One-time setup

```bash
# Python 3.11 backend venv
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Frontend deps
cd ../frontend
npm install

# Optional: Playwright browsers for the standing e2e suite
cd ../e2e
npm install
npx playwright install --with-deps chromium

# Local .env at repo root (gitignored). Copy from .env.example and fill in:
#   TASKS_JWT_SECRET — `openssl rand -hex 32`
#   TASKS_TEST_USER_EMAIL / TASKS_TEST_USER_PASSWORD — admin@tallied.dev creds
```

### Local dev — services

```bash
# Spin up dev DB (port 5434) + test DB (port 5433). Both are gitignored data.
docker compose up -d db db-test

# Apply migrations to dev DB (also runs automatically inside the container)
cd backend && .venv/bin/alembic upgrade head

# Backend on http://127.0.0.1:8001 with hot-reload
.venv/bin/uvicorn app.main:app --reload --port 8001

# Frontend on http://localhost:5173 (Vite proxies /api to :8001)
cd ../frontend && npm run dev
```

Login at http://localhost:5173 with the test-user credentials.

### Tests + lint

```bash
# Backend
cd backend
.venv/bin/pytest                       # all tests
.venv/bin/pytest -k transition         # name match
.venv/bin/pytest --cov=app             # with coverage
.venv/bin/ruff check . && .venv/bin/black --check .
.venv/bin/ruff check --fix . && .venv/bin/black .   # auto-fix

# Standing E2E (needs backend + frontend running, OR a built container on 8000)
cd e2e
BASE_URL=http://localhost:5173 npm test     # against vite dev
BASE_URL=http://localhost:8000 npm test     # against built container
```

### Migrations

```bash
cd backend
# After editing models, generate a new migration:
.venv/bin/alembic revision --autogenerate -m "add foo to bar"
# Review the generated file under alembic/versions/, then apply:
.venv/bin/alembic upgrade head
# Roll back one step:
.venv/bin/alembic downgrade -1
```

### Docker

```bash
# Build the prod image
DOCKER_BUILDKIT=1 docker build -t ghcr.io/mcheli/tasks:dev .

# Run the prod image against the dev DB on the local network
docker run --rm --name tasks-prod \
  --network tasks_default \
  -e TASKS_DATABASE_URL=postgresql+asyncpg://cycle_todo:changeme@db:5432/cycle_todo \
  -e TASKS_JWT_SECRET=dev-only \
  -e TASKS_TEST_USER_EMAIL=admin@tallied.dev \
  -e TASKS_TEST_USER_PASSWORD=tallied-admin-change-me \
  -e TASKS_ALLOWED_ORIGINS=http://localhost:8002 \
  -p 8002:8000 \
  ghcr.io/mcheli/tasks:dev

# Tail container logs
docker logs -f tasks-prod
```

### Git / CI

```bash
git status                             # check what's uncommitted
git log --oneline                      # see history (9 phase commits + 1 docs)
git push                               # push to origin/main → triggers release.yml
```

CI runs on every PR and push to main:
- `backend` job — ruff, black, pytest with coverage
- `frontend` job — npm ci, lint (warnings non-blocking), build
- `docker` job — full multi-stage build (no push)

Release workflow runs on push to main and on `v*` tags:
- Builds and pushes `ghcr.io/mcheli/tasks` with `:latest`, `:{sha}`, and `:v{semver}` tags

### Ports / hosts (local)

| Service | Port | URL |
|---|---|---|
| Postgres dev | 5434 (host) → 5432 | `postgresql://cycle_todo:changeme@localhost:5434/cycle_todo` |
| Postgres test | 5433 (host) → 5432 | `postgresql://postgres:postgres@localhost:5433/cycle_todo_test` |
| Backend (uvicorn) | 8001 | http://127.0.0.1:8001/api/health |
| Frontend (Vite) | 5173 | http://localhost:5173 |
| Built container (optional) | 8002 → 8000 | http://localhost:8002 |

### Environment variables

All variables are `TASKS_`-prefixed. Full table in `DEPLOYMENT_HANDOFF_TEMPLATE.md`. Local `.env` is gitignored; `.env.example` is the schema.

### Files to read first when coming back

1. `DECISIONS.md` — every judgment call made during the build, with rationale.
2. `DEPLOYMENT_HANDOFF_TEMPLATE.md` — self-contained ops manual for the deployment agent.
3. `ARCHITECTURE.md` + `DATABASE_SCHEMA.md` + `API_SPEC.md` — original spec; still accurate where DECISIONS.md doesn't override.

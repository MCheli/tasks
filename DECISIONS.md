# Decisions Log

Judgment calls made by the implementation agent. Each entry: what was decided, why, and what doc spec it conflicts with (if any).

Format:
```
## YYYY-MM-DD HH:MM — Title
**Decision:** ...
**Rationale:** ...
**Conflicts with:** ... (or "none")
```

---

## 2026-04-19 — Reference repo path
**Decision:** Use `~/repos/personal-finance/` as the structural reference repo wherever the docs say `~/repos/tallied/`.
**Rationale:** No `tallied/` directory exists. Mark confirmed `personal-finance/` is the same project (formerly named Tallied — the test user `admin@tallied.dev` lives in its `.env`).
**Conflicts with:** AGENT_INSTRUCTIONS.md, BACKEND_IMPLEMENTATION.md, README.md (all reference `~/repos/tallied/`).

## 2026-04-19 — Image name
**Decision:** Container image is `ghcr.io/mcheli/tasks` (not `ghcr.io/mcheli/cycle-todo` as the docs suggested).
**Rationale:** Mark chose this so it matches the GitHub repo name (`MCheli/tasks`). GHCR namespaces are lowercase, so `mcheli/tasks`.
**Conflicts with:** DEPLOYMENT.md, DEPLOYMENT_HANDOFF_TEMPLATE.md, AGENT_INSTRUCTIONS.md (all use `cycle-todo`). Updated those docs.

## 2026-04-19 — Env var prefix
**Decision:** All app env vars use a `TASKS_` prefix (e.g. `TASKS_DATABASE_URL`, `TASKS_JWT_SECRET`, `TASKS_TEST_USER_EMAIL`).
**Rationale:** Mark's choice — matches the `FINANCE_` convention in `personal-finance/`. Avoids collisions if multiple apps share a host or env file.
**Conflicts with:** BACKEND_IMPLEMENTATION.md, DEPLOYMENT.md, DEPLOYMENT_HANDOFF_TEMPLATE.md (all use unprefixed names). Updated those docs and `pydantic-settings` config (`env_prefix="TASKS_"`).

## 2026-04-19 — Reorder endpoint canonical
**Decision:** Drag-to-reorder uses `POST /api/tasks/{id}/reorder`. PATCH on `position` is also supported (single-field update) but UI never sends it for drag-drop.
**Rationale:** API spec defines both; the dedicated endpoint is clearer about intent (resequencing) and returns the full reordered list.
**Conflicts with:** none — both endpoints exist per spec; this just documents which the UI uses.

## 2026-04-19 — Position carry-forward keeps sparse positions
**Decision:** When tasks are forwarded to a new cycle, they keep their original `position` value (potentially sparse, e.g. 1, 4, 7 if positions 2/3/5/6 were completed/canceled). Positions are NOT compacted on transition.
**Rationale:** Spec says "carried-forward tasks retain their position." Compaction would require the user to think about position renumbering on every transition, and sparse positions are invisible to the user (the UI just orders by position ascending).
**Conflicts with:** none.

## 2026-04-19 — Soft delete is lineage-wide
**Decision:** `DELETE /api/tasks/{id}` soft-deletes every row sharing the same `persistent_task_id` for that user. UI confirm dialog says "Delete this task and all its history?"
**Rationale:** Matches API_SPEC.md explicit behavior. The dialog copy makes the scope clear so users aren't surprised.
**Conflicts with:** none.

## 2026-04-19 — Historical cycle view is read-only
**Decision:** `/cycle/:cycleId` for any cycle whose `ended_at IS NOT NULL` renders all task interactions disabled. No checkbox toggle, no inline edit, no reorder, no kebab menu. Only "view" affordances (expand to read notes/metadata).
**Rationale:** Matches API constraint that historical rows return 403 on PATCH; UI just enforces what the API enforces.
**Conflicts with:** none.

## 2026-04-19 — Task expansion auto-save behavior
**Decision:** Inline task edits require explicit Save click (or Cmd+Enter). No auto-save on blur.
**Rationale:** Spec says "implementer's choice, document it." Explicit save avoids accidental edits when a user clicks away mid-edit.
**Conflicts with:** none.

## 2026-04-19 — Three-state action picker style
**Decision:** Single button per task in TransitionView that cycles through `→ / ✓ / ✗` on click. Color changes (accent/green/red).
**Rationale:** Spec offered two options; cycler is cleaner on mobile (one tap target instead of three).
**Conflicts with:** none.

## 2026-04-19 — Static dir path inside container
**Decision:** Frontend build is copied to `/app/static/` and `main.py` resolves the directory via `Path("/app/static")` (or via `BASE_DIR` env, defaulting to that). The `Path(__file__).parent.parent / "static"` snippet in BACKEND_IMPLEMENTATION.md is wrong — from `/app/backend/app/main.py` that resolves to `/app/backend/static`, which doesn't exist.
**Rationale:** Need the path to match the Dockerfile's `COPY --from=frontend-build /app/frontend/dist ./static/` line (which puts files at `/app/static/`). Backend `main.py` lives at `/app/backend/app/main.py`.
**Conflicts with:** BACKEND_IMPLEMENTATION.md path snippet.

## 2026-04-19 — PYTHONPATH and module layout in container
**Decision:** Container entrypoint runs `cd /app/backend && alembic upgrade head` (so `app.config` resolves) and uvicorn is invoked as `uvicorn app.main:app` from `/app/backend` (via WORKDIR). The Dockerfile's `CMD ["uvicorn", "backend.app.main:app", ...]` snippet is wrong — it would only work with `/app` as CWD AND with a `backend/__init__.py`, neither of which is desirable.
**Rationale:** Cleanest: `WORKDIR /app/backend` for runtime; alembic.ini and alembic/ live under `/app/backend/`, not `/app/`. Path imports like `app.config` work without prefix gymnastics.
**Conflicts with:** DEPLOYMENT.md Dockerfile CMD line.

## 2026-04-19 — Dev hot-reload command
**Decision:** Dev mode runs `uvicorn app.main:app --reload` via a Compose override (`docker-compose.override.yml`) that mounts the source bind mount and overrides CMD. Production CMD stays `--workers 2`.
**Rationale:** Hot-reload requires `--reload` (single worker). Production needs multiple workers. Compose override keeps the prod Dockerfile clean.
**Conflicts with:** none — fills a gap.

## 2026-04-19 — Cross-user isolation tests
**Decision:** Tests insert a second user (`bob@test.local`) directly via DB fixture. No public signup endpoint exists; this is the only way to create a second user.
**Rationale:** Mark wants Google SSO as the only signup path for real users. Test user (1st) is seeded from env vars. Test isolation requires a 2nd user inserted at the DB layer in the test fixture.
**Conflicts with:** none.

## 2026-04-19 — Vitest skipped for v1
**Decision:** Don't add Vitest. Frontend tests rely on E2E (Playwright) only.
**Rationale:** Spec says vitest unit tests are optional. The composables and stores in this app are thin enough that E2E coverage is sufficient.
**Conflicts with:** none — spec explicitly allows.

## 2026-04-19 — Playwright MCP installation
**Decision:** Added `playwright` MCP server via `claude mcp add`. Activates next session. For *this* build session, in-session UI verification uses `Claude_in_Chrome` MCP and the standing `e2e/` suite (commits to repo, runs in CI).
**Rationale:** New MCPs aren't available mid-session.
**Conflicts with:** none.

## 2026-04-19 — Local Python 3.11 install
**Decision:** Installed Python 3.11 via Homebrew so backend tests can run locally without Docker. Container still pins 3.11.
**Rationale:** Faster iteration than `docker compose run` for every test cycle.
**Conflicts with:** none.

## 2026-04-19 — Health endpoints prefix
**Decision:** Health is at `/api/health` and `/api/health/db` (under the `/api` prefix). The Dockerfile's healthcheck and DEPLOYMENT_HANDOFF_TEMPLATE both use `/api/health`, which matches.
**Rationale:** Consistency — every backend endpoint sits under `/api`.
**Conflicts with:** none.

## 2026-04-19 — Dev DB port moved to 5434
**Decision:** Local dev Postgres listens on host port 5434 (instead of 5432). Test DB stays at 5433.
**Rationale:** The host already has a Postgres on 5432 from the personal-finance project (`tallied-postgres` container). Avoid the collision so both projects can run side-by-side.
**Conflicts with:** DEPLOYMENT.md/`.env.example` (originally said 5432). Updated.

## 2026-04-19 — Local dev API port moved to 8001
**Decision:** Local-dev backend runs on host port 8001 (not 8000). Inside the container the app still listens on 8000; only the host port mapping changes (`8001:8000`). Vite dev proxy targets `localhost:8001`.
**Rationale:** Host port 8000 is occupied by another project's backend (personal-finance). 8001 keeps the projects independent.
**Conflicts with:** README.md / DEPLOYMENT.md (referenced :8000 for local). Production NGINX still proxies to container port 8000.

## 2026-04-19 — display_id uniqueness rule
**Decision:** `display_id` is unique per *lineage* (per `persistent_task_id`), not per row. The DATABASE_SCHEMA.md `UNIQUE (user_id, display_id)` constraint is replaced with a non-unique INDEX. The `display_id_sequences` allocator only issues a new integer on `create_task` (when a new `persistent_task_id` is minted), so duplicates within a user can only happen across rows of the same lineage — which is the intent (so users can refer to "task #42" across cycles).
**Rationale:** The schema spec was internally inconsistent: it requires forwarded rows to share `display_id` *and* requires `(user_id, display_id)` to be unique. Both can't hold. Forwarded-rows-share-display-id is the user-visible behavior, so that wins.
**Conflicts with:** DATABASE_SCHEMA.md §tasks indexes block.

## 2026-04-19 — Cycle transition row ordering
**Decision:** During `transition_cycle`, the old cycle's `ended_at` is set BEFORE the new cycle is inserted. Without this, the partial-unique index `(user_id, category) WHERE ended_at IS NULL` fires immediately on the new INSERT (Postgres evaluates partial unique indexes synchronously, not at commit).
**Rationale:** Partial UNIQUE indexes can't be DEFERRABLE in Postgres. Reordering the writes is cheaper than restructuring the constraint.
**Conflicts with:** DATABASE_SCHEMA.md §"Example: Cycle Transition" lists steps in the opposite order. Functionally equivalent; this version actually works.

## 2026-04-19 — Vue draggable lib version
**Decision:** Use `vuedraggable@4.1.0` (the Vue 3 compatible release line).
**Rationale:** Earlier 2.x line is Vue 2 only.
**Conflicts with:** none.

# API Specification

All endpoints are under the `/api` prefix. All requests and responses use `application/json`. Auth is via an httpOnly cookie named `session` containing a JWT.

Status codes:
- `200` — OK
- `201` — Created
- `204` — No Content
- `400` — Bad request (validation error, Pydantic returns detail with field errors)
- `401` — Not authenticated
- `403` — Authenticated but forbidden (e.g., trying to access another user's data)
- `404` — Not found
- `409` — Conflict (e.g., trying to create a cycle when a current one already exists)
- `422` — Unprocessable entity (Pydantic validation errors are typically here)

## Authentication

### `POST /api/auth/login`
Log in with email and password.

**Request:**
```json
{"email": "user@example.com", "password": "secret"}
```

**Response 200:**
```json
{"user": {"id": "...", "email": "...", "display_name": null}}
```
Sets `session` httpOnly cookie. `Secure` in production, `SameSite=Lax`.

**Response 401:** `{"detail": "Invalid credentials"}`

### `POST /api/auth/logout`
Clear the session cookie.

**Response 204** (no body).

### `GET /api/auth/me`
Return the currently authenticated user.

**Response 200:**
```json
{"id": "...", "email": "...", "display_name": null}
```

**Response 401** if no valid cookie.

### `POST /api/auth/demo`

Public demo only (`TASKS_DEMO_MODE=true`). Signs in as the demo persona (`TASKS_DEMO_USER_EMAIL`, default `claudius@tasks.dev`) with no password and sets the `session` cookie. Response as for `/login`.

- `404` outside demo mode.
- `503` if the persona isn't in the database yet (the nightly reseed is running).

### `GET /api/auth/config`

What the login page needs to know about this deployment. No auth.

```json
{ "google_configured": true, "demo_mode": false, "demo_url": "https://tasks-demo.markcheli.com" }
```

### Demo mode

In demo mode every `POST`/`PUT`/`PATCH`/`DELETE` except `POST /api/auth/demo` and `POST /api/auth/logout` answers `403 {"detail": "...", "demo": true}`, every response carries `X-Robots-Tag: noindex, nofollow`, and `GET /api/cycles/current` answers `503` rather than creating a missing cycle. See `backend/app/demo.py`.

### `GET /api/auth/google/login`
*(Scaffolded, not yet wired to real Google credentials.)* Redirects to Google consent screen.

### `GET /api/auth/google/callback`
*(Scaffolded, not yet wired.)* Handles the OAuth code exchange, creates or loads the user, sets session cookie, redirects to `/`.

## Cycles

### Owners: Mark's list and the agents' list

Since 2026-11-23 every task has an `owner`: `human` (Mark's own to-do list; everything created without saying otherwise, so the Chore tracker and older clients are unaffected) or `agent` (the follow-up list that Claude agents use through the MCP connector). Agent items also carry `source`, `link`, `agent_status` (`open | in_progress | blocked | done`) and a notes log. `agent_status: done` and `status: completed` always go together.

Every list endpoint takes `owner={human|agent|all}` and **defaults to `human`**, so existing clients see exactly what they used to. To fetch the agents' items ask for `owner=agent`; `owner=all` returns both.

### `GET /api/cycles/current?category={personal|professional}&owner={human|agent|all}`
Return the user's currently active cycle for the given category, along with its tasks (of that owner). Auto-creates the first cycle if none exists.

**Response 200:**
```json
{
  "cycle": {
    "id": "uuid",
    "category": "personal",
    "started_at": "2026-04-19T14:30:00Z",
    "ended_at": null,
    "next_cycle_id": null
  },
  "tasks": {
    "open": [Task, Task, ...],
    "completed": [Task, ...],
    "canceled": [Task, ...]
  },
  "summary": {"open": 5, "completed": 2, "canceled": 1}
}
```

Tasks are sorted by `position` ascending within each group.

### `GET /api/cycles?category={personal|professional}&limit=50&offset=0`
List cycles for the user and category, most recent first.

**Response 200:**
```json
{
  "cycles": [
    {
      "id": "uuid",
      "category": "personal",
      "started_at": "...",
      "ended_at": "...",
      "next_cycle_id": "...",
      "task_counts": {"open": 0, "completed": 5, "canceled": 1}
    }
  ],
  "total": 12
}
```

### `GET /api/cycles/{cycle_id}`
Full detail of a specific cycle, including all (non-deleted) tasks.

**Response 200:** Same shape as `/current`.
**Response 404** if not found or not owned.

### `POST /api/cycles/{cycle_id}/transition`
Close the given cycle and create the next one. `cycle_id` must be the user's currently active cycle for its category.

**Request:**
```json
{
  "actions": [
    {"persistent_task_id": "uuid", "action": "forward"},
    {"persistent_task_id": "uuid", "action": "complete"},
    {"persistent_task_id": "uuid", "action": "cancel"}
  ]
}
```

Rules:
- Every open task of Mark's list (`owner=human`) in the old cycle MUST appear in `actions`. Missing tasks → 400.
- Open agent items need no action: they are forwarded to the new cycle on their own (keeping status, source, link and the notes log). An action given for one is honored.
- `actions` MUST NOT reference already-completed or already-canceled tasks. → 400.
- Valid actions: `forward`, `complete`, `cancel`.

**Response 201:**
```json
{
  "old_cycle": {...},
  "new_cycle": {...},
  "new_cycle_tasks": {"open": [...], "completed": [], "canceled": []},
  "summary": {"forwarded": 5, "completed": 2, "canceled": 1}
}
```

**Response 409** if the cycle is already closed.

## Tasks

### `POST /api/tasks`
Create a new task in the user's current cycle for the given category.

**Request:**
```json
{
  "category": "personal",
  "title": "Buy groceries",
  "notes": "Optional longer text with links etc",
  "owner": "human",            // optional; default human. "agent" for the agents' list
  "source": "weekly-security-sweep",   // agent items: who made it (optional)
  "link": "https://github.com/MCheli/tasks/pull/12",   // optional
  "agent_status": "open"       // agent items: open | in_progress | blocked | done (default open)
}
```

**Response 201:**
```json
{"task": Task}
```

If the user has no current cycle for this category, one is created automatically before the task.

### `GET /api/tasks?category=&owner=all&status=&q=&include_done=false&limit=100`
Flat list of tasks in the current cycle(s), newest cycle first within position order. Without `category` both lists are included. `owner` defaults to **`all`** here (this endpoint is new). `status` is `open | completed | canceled` or an agent status (`in_progress | blocked | done`, where done = completed). Without `status`, only open items are returned unless `include_done=true`. `q` matches title, notes, source and link.

**Response 200:** `{"tasks": [Task, ...]}`

### `GET /api/tasks/overview`
All four lists in one call, for the ambient display: open items plus counts for `{personal, professional} × {human, agent}`.

**Response 200:**
```json
{
  "personal": {
    "cycle_id": "uuid or null",
    "human": {"open": [Task, ...], "counts": {"open": 3, "completed": 5, "canceled": 0}},
    "agent": {"open": [Task, ...], "counts": {"open": 2, "completed": 1, "canceled": 0, "in_progress": 1, "blocked": 0}}
  },
  "professional": { ...same shape... }
}
```

### `PATCH /api/tasks/{task_id}`
Update a task. All fields optional; only provided fields are updated.

**Request:**
```json
{
  "title": "New title",
  "notes": "Updated notes",
  "status": "completed",   // or "open" or "canceled"
  "position": 3,
  "source": "...", "link": "...",      // agent fields
  "agent_status": "in_progress"        // agent items: open | in_progress | blocked | done
}
```

- `task_id` is the per-row UUID, not the persistent_task_id.
- Only tasks belonging to the user's current cycle are editable via PATCH. Historical rows are immutable. → 403 if trying to edit historical.
- Changing `status` to `completed` sets `completed_at`. To `canceled` sets `canceled_at`. To `open` clears both.
- Agent items: `agent_status: done` completes the task; `status: completed` marks it done; any other `agent_status` reopens a done item; `status: open` puts a done item back to `open`. `agent_status` is ignored for human items.
- Changing `position` triggers a reorder among the open tasks of the same owner in the same cycle.

**Response 200:** `{"task": Task}`

### `POST /api/tasks/{task_id}/notes`
Append an entry to the task's notes log (allowed on historical rows too; the log belongs to the lineage).

**Request:** `{"body": "Opened PR #12", "author": "weekly-security-sweep"}` — `author` is optional and defaults to the API key's name, else the signed-in user.

**Response 201:** `{"note": {"id", "author", "body", "created_at"}, "task": Task}`

### `POST /api/tasks/{task_id}/reorder`
Explicit reorder endpoint for drag-and-drop. Accepts a new position and resequences the list.

**Request:**
```json
{"new_position": 2}
```

**Response 200:**
```json
{"tasks": [Task, Task, ...]}  // full reordered list for the cycle/status
```

### `DELETE /api/tasks/{task_id}`
Soft delete. Sets `deleted_at = NOW()` on the task row. The task vanishes from all views including history.

Note: this only deletes the single row. If the user wants the entire lineage gone, the server should also soft-delete all rows sharing the same `persistent_task_id` (within the user's scope). **This is the default behavior** — deletion is always lineage-wide.

**Response 204.**

### `GET /api/tasks/{task_id}`
Fetch a single task including derived history.

**Response 200:**
```json
{
  "task": Task,
  "lineage": [
    {
      "cycle_id": "...",
      "cycle_started_at": "...",
      "cycle_ended_at": "...",
      "status_at_end": "open",
      "position": 1
    }
  ],
  "push_forward_count": 3,
  "notes_log": [{"id": "...", "author": "weekly-security-sweep", "body": "...", "created_at": "..."}]
}
```

`lineage` is ordered oldest → newest; `notes_log` oldest first.

## Task Schema (response shape)

```json
{
  "id": "uuid",
  "persistent_task_id": "uuid",
  "display_id": 42,
  "cycle_id": "uuid",
  "previous_task_id": "uuid or null",
  "title": "string",
  "notes": "string or null",
  "status": "open | completed | canceled",
  "position": 0,
  "push_forward_count": 2,   // derived, included inline
  "owner": "human | agent",
  "source": "string or null",          // agent items
  "link": "string or null",            // agent items
  "agent_status": "open | in_progress | blocked | done | null",   // null for human items
  "note_count": 0,           // derived: entries in the notes log
  "created_at": "2026-04-19T14:30:00Z",
  "updated_at": "2026-04-19T14:35:00Z",
  "completed_at": "... or null",
  "canceled_at": "... or null"
}
```

## History

### `GET /api/history?category={personal|professional}&owner={human|agent|all}`
All task lineages for the user and category (default: Mark's own items), shaped for the Gantt chart.

**Response 200:**
```json
{
  "cycles": [
    {"id": "...", "started_at": "...", "ended_at": "..."}
  ],
  "lineages": [
    {
      "persistent_task_id": "uuid",
      "display_id": 42,
      "title": "Buy groceries",
      "latest_status": "open",
      "first_seen_at": "2026-04-01T00:00:00Z",
      "last_seen_at": "2026-04-19T14:30:00Z",
      "push_forward_count": 3,
      "spans": [
        {
          "cycle_id": "...",
          "started_at": "...",
          "ended_at": "...",
          "status_at_end": "open"
        }
      ]
    }
  ]
}
```

The frontend renders each `lineage` as a horizontal row; each `span` is a segment of that row colored by `status_at_end`.

## Health

### `GET /api/health`
Simple liveness probe.

**Response 200:** `{"status": "ok"}`

### `GET /api/health/db`
Verifies DB connectivity.

**Response 200:** `{"status": "ok", "db": "ok"}`
**Response 503:** `{"status": "degraded", "db": "unreachable"}`

## Error Response Shape

FastAPI default `{"detail": "..."}`. For validation errors, FastAPI returns a list under `detail`:

```json
{
  "detail": [
    {"loc": ["body", "title"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

Frontend should accept either form.

## MCP connector (`/mcp`)

The app is also a remote MCP server (streamable HTTP, stateless, JSON responses) at `<TASKS_PUBLIC_URL>/mcp`, built with the official `mcp` SDK (`backend/app/mcp/`). It is only mounted when `TASKS_PUBLIC_URL` is set and never in demo mode.

**Auth.** `Authorization: Bearer <token>` where the token is either an OAuth 2.1 access token issued by the app itself (claude.ai custom connector: dynamic client registration at `/register`, PKCE S256 at `/authorize`, `/token`, `/revoke`; metadata at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/mcp`) or one of the app's API keys (`tsk_…`), so scheduled jobs skip OAuth. No token → `401` with `WWW-Authenticate: Bearer … resource_metadata="…"`. The connector's Google sign-in reuses the app's Google OAuth client and its registered redirect URI (`/api/auth/google/callback`, told apart by a state signed by the app); only verified accounts listed in `TASKS_MCP_ALLOWED_EMAILS` that are already users may sign in, and no users are ever created by it.

**Tools.** `list_tasks(list, owner, status, query, include_done, limit)`, `get_task(task)`, `create_task(title, list, owner="agent", status, source, link, notes)`, `update_task(task, title, status, source, link, notes)`, `complete_task(task, note)`, `reopen_task(task, note)`, `add_note(task, body, author)`. `task` is an id or a `#number`. Output is compact JSON (`id, number, title, list, owner, status, source, link, notes, note_count, updated_at`; `notes_log` on get_task/add_note). There is no delete tool.

## Command-line helper (`scripts/tasks-agent`)

For agents with a shell but no MCP connector (Claude Code sessions on the Mac mini, scripts). One Python 3 file, standard library only; installed on the Mac mini as `~/.local/bin/tasks-agent`. It talks to the REST API above with `X-API-Key`: the key comes from `TASKS_API_KEY`, else `agent-op read "$TASKS_API_KEY_OP_REF"` (default `op://Agents/Tasks API key/credential`); `TASKS_URL` overrides `https://tasks.markcheli.com`. It never prints the key; a 401 prints `auth failed`.

Defaults are `--list personal` and the agent list. A task is `#123`, `123` or a UUID, looked up among the current cycle's items of the chosen list.

```
tasks-agent list [--status S] [--query Q] [--all-owners] [--include-done] [--json]
tasks-agent find QUERY                       # open agent items matching title/notes/source/link
tasks-agent create TITLE --source S [--link URL] [--notes TEXT] [--status open|in_progress|blocked] [--if-missing]
tasks-agent update REF [--status open|in_progress|blocked|done] [--title T] [--link URL] [--source S]
tasks-agent note REF BODY [--author A]
tasks-agent done REF [--note BODY] [--author A]
tasks-agent get REF                          # item plus its notes log
```

`--if-missing` prints the open agent item with the same title (case-insensitive) or the same link and exits 0 instead of creating a duplicate. Output is one line per item, `#N [status] title (source) link`; `--json` gives the API's JSON. Errors are one line on stderr with exit code 1. Tests: `python3 -m unittest discover -s tests/scripts` (run in CI).

## Rate Limiting

Out of scope for v1. Add if/when needed.

## CORS

Configured via `ALLOWED_ORIGINS` env var. In local dev, include `http://localhost:5173`. In production, the frontend is same-origin so CORS is effectively a no-op.

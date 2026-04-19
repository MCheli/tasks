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

### `GET /api/auth/google/login`
*(Scaffolded, not yet wired to real Google credentials.)* Redirects to Google consent screen.

### `GET /api/auth/google/callback`
*(Scaffolded, not yet wired.)* Handles the OAuth code exchange, creates or loads the user, sets session cookie, redirects to `/`.

## Cycles

### `GET /api/cycles/current?category={personal|professional}`
Return the user's currently active cycle for the given category, along with its tasks. Auto-creates the first cycle if none exists.

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
- Every open task in the old cycle MUST appear in `actions`. Missing tasks → 400.
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
  "notes": "Optional longer text with links etc"
}
```

**Response 201:**
```json
{"task": Task}
```

If the user has no current cycle for this category, one is created automatically before the task.

### `PATCH /api/tasks/{task_id}`
Update a task. All fields optional; only provided fields are updated.

**Request:**
```json
{
  "title": "New title",
  "notes": "Updated notes",
  "status": "completed",   // or "open" or "canceled"
  "position": 3
}
```

- `task_id` is the per-row UUID, not the persistent_task_id.
- Only tasks belonging to the user's current cycle are editable via PATCH. Historical rows are immutable. → 403 if trying to edit historical.
- Changing `status` to `completed` sets `completed_at`. To `canceled` sets `canceled_at`. To `open` clears both.
- Changing `position` triggers a reorder: other tasks in the same cycle shift to accommodate.

**Response 200:** `{"task": Task}`

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
  "push_forward_count": 3
}
```

`lineage` is ordered oldest → newest.

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
  "created_at": "2026-04-19T14:30:00Z",
  "updated_at": "2026-04-19T14:35:00Z",
  "completed_at": "... or null",
  "canceled_at": "... or null"
}
```

## History

### `GET /api/history?category={personal|professional}`
All task lineages for the user and category, shaped for the Gantt chart.

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

## Rate Limiting

Out of scope for v1. Add if/when needed.

## CORS

Configured via `ALLOWED_ORIGINS` env var. In local dev, include `http://localhost:5173`. In production, the frontend is same-origin so CORS is effectively a no-op.

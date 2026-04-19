# Database Schema

PostgreSQL 15. All timestamps are `TIMESTAMPTZ` (UTC). All IDs are UUIDs except `display_id` which is an integer. Soft delete is a `deleted_at` column; any query that could see user-visible tasks must filter `WHERE deleted_at IS NULL`.

## Tables

### `users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT `gen_random_uuid()` | |
| `email` | VARCHAR(255) | UNIQUE NOT NULL | Used as login identity |
| `hashed_password` | VARCHAR(255) | NULLABLE | NULL for Google-SSO-only users |
| `google_sub` | VARCHAR(255) | UNIQUE NULLABLE | Google OAuth `sub` claim |
| `display_name` | VARCHAR(255) | NULLABLE | From Google or manually set |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Updated on UPDATE |

Indexes:
- UNIQUE on `email`
- UNIQUE on `google_sub` WHERE `google_sub IS NOT NULL`

### `cycles`

Each cycle is a planning interval for a specific user and category. A user can have at most one "current" (end-date-null) cycle per category at any time.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT `gen_random_uuid()` | |
| `user_id` | UUID | FK → users.id, NOT NULL, ON DELETE CASCADE | |
| `category` | VARCHAR(20) | NOT NULL, CHECK IN ('personal','professional') | |
| `started_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `ended_at` | TIMESTAMPTZ | NULLABLE | NULL = current/active cycle |
| `next_cycle_id` | UUID | FK → cycles.id, NULLABLE | Set when transition occurs |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

Indexes:
- `(user_id, category, ended_at)` — primary query pattern ("find my current cycle")
- `(user_id, category, started_at DESC)` — for history listing
- Partial UNIQUE: `(user_id, category) WHERE ended_at IS NULL` — enforce "only one current cycle per user/category"

### `tasks`

Each row is one task's snapshot *in one cycle*. A task's identity across cycles is `persistent_task_id`. Position, status, and notes are all per-cycle.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT `gen_random_uuid()` | Row ID (per-cycle) |
| `persistent_task_id` | UUID | NOT NULL | Shared across a task's cycle lineage |
| `display_id` | INTEGER | NOT NULL | Per-user incrementing integer |
| `user_id` | UUID | FK → users.id, NOT NULL, ON DELETE CASCADE | |
| `cycle_id` | UUID | FK → cycles.id, NOT NULL, ON DELETE CASCADE | |
| `previous_task_id` | UUID | FK → tasks.id, NULLABLE | Row in the prior cycle that this was forwarded from |
| `title` | VARCHAR(500) | NOT NULL | |
| `notes` | TEXT | NULLABLE | Optional longer-form body / links |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'open', CHECK IN ('open','completed','canceled') | |
| `position` | INTEGER | NOT NULL DEFAULT 0 | Lower = higher in list |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `completed_at` | TIMESTAMPTZ | NULLABLE | Set when status → 'completed' |
| `canceled_at` | TIMESTAMPTZ | NULLABLE | Set when status → 'canceled' |
| `deleted_at` | TIMESTAMPTZ | NULLABLE | Soft delete timestamp |

Indexes:
- `(cycle_id, deleted_at, status, position)` — the primary list query
- `(user_id, persistent_task_id)` — lineage lookup
- `(user_id, display_id)` — lookup by display ID
- UNIQUE `(user_id, display_id)` — display IDs are unique per user
- `(previous_task_id)` — walking the lineage backward

### `display_id_sequences`

Per-user counter for `tasks.display_id`. Implemented as a table rather than a Postgres sequence because display IDs are user-scoped, and Postgres sequences aren't easily parameterized per user.

| Column | Type | Constraints |
|---|---|---|
| `user_id` | UUID | PK, FK → users.id, ON DELETE CASCADE |
| `next_value` | INTEGER | NOT NULL DEFAULT 1 |

Allocation is done inside a transaction with `SELECT ... FOR UPDATE` on this row:

```sql
UPDATE display_id_sequences
SET next_value = next_value + 1
WHERE user_id = $1
RETURNING next_value - 1;
```

Or use an atomic `RETURNING` increment pattern.

### `alembic_version`

Standard Alembic migration tracking table. Don't touch manually.

## Relationships

```
users (1) ──< cycles (many)
users (1) ──< tasks (many)
users (1) ──── display_id_sequences (1)
cycles (1) ──< tasks (many)
tasks (1) ──── tasks (1 via previous_task_id)  -- self-ref chain forming a linked list per persistent_task_id
cycles (1) ──── cycles (1 via next_cycle_id)   -- linked list of cycles over time
```

## Derived Quantities (Do NOT Store)

### Push-forward count for a task
```sql
SELECT COUNT(*) - 1
FROM tasks
WHERE persistent_task_id = $1 AND user_id = $2 AND deleted_at IS NULL;
```
(Count of rows sharing the persistent ID, minus 1 for the original creation row.)

### Push-forward history (timestamps)
```sql
SELECT t.created_at, c.started_at AS cycle_start
FROM tasks t JOIN cycles c ON t.cycle_id = c.id
WHERE t.persistent_task_id = $1 AND t.user_id = $2 AND t.deleted_at IS NULL
ORDER BY c.started_at ASC;
```

### Cycle summary (open / completed / canceled counts)
```sql
SELECT status, COUNT(*)
FROM tasks
WHERE cycle_id = $1 AND deleted_at IS NULL
GROUP BY status;
```

## Example: Creating a Task

1. Begin transaction.
2. `SELECT ... FOR UPDATE` on `display_id_sequences` for the user; increment.
3. `INSERT INTO tasks` with a fresh `persistent_task_id = gen_random_uuid()`, the allocated `display_id`, the user's current cycle for the requested category, `previous_task_id = NULL`, `status = 'open'`, `position = (MAX(position) + 1 in that cycle)`.
4. Commit.

## Example: Cycle Transition

The client sends `POST /api/cycles/{old_cycle_id}/transition` with a body like:

```json
{
  "actions": [
    {"persistent_task_id": "...", "action": "forward"},
    {"persistent_task_id": "...", "action": "complete"},
    {"persistent_task_id": "...", "action": "cancel"}
  ]
}
```

Server logic, all in one transaction:

1. Verify `old_cycle_id` belongs to the current user and `ended_at IS NULL`.
2. For each `action: complete`, `UPDATE` the corresponding open task row in the old cycle: `status = 'completed', completed_at = NOW()`.
3. For each `action: cancel`, same but `status = 'canceled', canceled_at = NOW()`.
4. Create the new cycle row: `INSERT INTO cycles (...) VALUES (...) RETURNING id`.
5. Update the old cycle: `ended_at = NOW(), next_cycle_id = <new_cycle_id>`.
6. For each `action: forward`, `INSERT` a new task row: same `persistent_task_id`, new `id`, new `cycle_id = <new>`, `previous_task_id = <old task row id>`, same `title` and `notes`, `status = 'open'`, same `position` as in the old cycle.
7. Commit.

If anything fails, rollback — the client must be able to retry safely.

## Migrations

Alembic. Initial migration creates all tables. Subsequent migrations for any schema change. Commit migration files to the repo.

Migration naming: `YYYYMMDD_HHMM_{slug}.py`, e.g. `20260419_1500_initial_schema.py`.

## Seeding

On app startup, if the `TEST_USER_EMAIL` env var is set and the user doesn't exist, create the test user with `TEST_USER_PASSWORD` hashed. This enables fresh-database local dev to just work.

Do NOT seed cycles or tasks — those are created on-demand the first time the user opens a category tab.

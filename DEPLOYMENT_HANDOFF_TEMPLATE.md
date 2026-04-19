# Tasks — Deployment Handoff

This is the only doc the deployment agent needs. Everything required to run the container in production is here.

## What this app is

Self-hosted, single-user (for now) cycle-based todo application. FastAPI backend + Vue 3 frontend, packaged into one Docker image. State lives in an external PostgreSQL 15+ database.

## Target environment

- **Domain:** `tasks.markcheli.com`
- **Host:** Mark's Dell PowerEdge R630, Ubuntu 24.04
- **Reverse proxy:** existing NGINX on the host
- **TLS:** Let's Encrypt or Cloudflare Origin (whichever pattern matches the rest of the homelab)
- **Container runtime:** Docker + Docker Compose (already on the host)

## Container image

- **Registry:** GitHub Container Registry (GHCR)
- **Image:** `ghcr.io/mcheli/tasks`
- **Tags:**
  - `:latest` — auto-built from every push to `main`
  - `:{sha}` — every commit (short sha used as tag)
  - `:v{semver}` — git tags matching `v*`
- **Internal port:** `8000` (HTTP). Behind NGINX.
- **Healthcheck:** `GET /api/health` → `{"status":"ok"}` 200. Already wired into the image's `HEALTHCHECK` directive.
- **Runs as:** non-root uid 1000 (user `app`). No special capabilities or volumes needed on the app container.
- **Persistent state:** none on the app container. Everything is in Postgres.

## Database

- PostgreSQL 15 or newer.
- Dedicated database + user recommended: db `cycle_todo`, user `cycle_todo`.
- Container must reach the DB host on its Postgres port (default 5432).
- **Migrations run automatically on startup** (`alembic upgrade head`). Safe to re-run; no-op once current.
- **Backups:** out of scope for this app. Recommend a daily `pg_dump` to the NAS, scheduled outside the container.

## Environment variables

All variables use the `TASKS_` prefix. The app reads them via pydantic-settings.

| Variable | Required | Description | Example |
|---|---|---|---|
| `TASKS_ENV` | yes | `production` to disable docs and require secure cookies. | `production` |
| `TASKS_ENABLE_DOCS` | no | `false` hides `/api/docs`. Default `true`. | `false` |
| `TASKS_DATABASE_URL` | yes | Async Postgres URL. Must use `postgresql+asyncpg://`. | `postgresql+asyncpg://cycle_todo:SECRET@db.internal:5432/cycle_todo` |
| `TASKS_JWT_SECRET` | yes | 32+ byte random hex. Generate: `openssl rand -hex 32`. | (64 hex chars) |
| `TASKS_JWT_ALGORITHM` | no | Default `HS256`. Leave as-is. | `HS256` |
| `TASKS_JWT_EXPIRE_DAYS` | no | Session lifetime. Default `7`. | `7` |
| `TASKS_COOKIE_SECURE` | yes (prod) | **Must be `true` behind HTTPS.** | `true` |
| `TASKS_COOKIE_DOMAIN` | no | Leave blank unless cross-subdomain SSO is wanted. | _(empty)_ |
| `TASKS_TEST_USER_EMAIL` | yes (until SSO) | Fallback login identity. Seeded on first startup if missing. | `claudius@markcheli.com` |
| `TASKS_TEST_USER_PASSWORD` | yes (until SSO) | Paired password. Same value as in Mark's existing dev `.env`. | _(from Mark)_ |
| `TASKS_GOOGLE_CLIENT_ID` | no | Google OAuth client ID. Leave blank until Mark completes Google Cloud Console setup. | `123.apps.googleusercontent.com` |
| `TASKS_GOOGLE_CLIENT_SECRET` | no | Paired Google OAuth secret. | `GOCSPX-...` |
| `TASKS_GOOGLE_REDIRECT_URI` | no | Must match exactly what's configured in Google Cloud Console. | `https://tasks.markcheli.com/api/auth/google/callback` |
| `TASKS_ALLOWED_ORIGINS` | yes | Comma-separated list. Production should be the exact prod URL. | `https://tasks.markcheli.com` |
| `TASKS_STATIC_DIR` | no | Override the static-files location (defaults to `/app/static`). | _(empty)_ |

**Secrets:** `TASKS_JWT_SECRET`, `TASKS_DATABASE_URL`, `TASKS_TEST_USER_PASSWORD`, `TASKS_GOOGLE_CLIENT_SECRET`. Pull from the deployment agent's secret manager. Never commit to a repo.

## Sample `docker-compose.yml` (production)

(Adapt to existing compose structure on the host.)

```yaml
services:
  tasks:
    image: ghcr.io/mcheli/tasks:latest
    restart: unless-stopped
    env_file: /opt/markcheli/tasks.env
    ports:
      - "127.0.0.1:8000:8000"   # bind to localhost; NGINX proxies
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    depends_on:
      - postgres
    networks: [homelab]

  # If a shared Postgres isn't already in this stack:
  postgres:
    image: postgres:15
    restart: unless-stopped
    environment:
      POSTGRES_DB: cycle_todo
      POSTGRES_USER: cycle_todo
      POSTGRES_PASSWORD: ${CYCLE_TODO_DB_PASSWORD}
    volumes:
      - cycle_todo_pg:/var/lib/postgresql/data
    networks: [homelab]

networks:
  homelab:
    external: true

volumes:
  cycle_todo_pg:
```

## NGINX (example — match existing pattern)

```nginx
server {
    listen 443 ssl http2;
    server_name tasks.markcheli.com;

    ssl_certificate     /etc/ssl/markcheli/fullchain.pem;
    ssl_certificate_key /etc/ssl/markcheli/privkey.pem;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

## Deployment steps

1. **Create the database** (if not sharing an existing PG instance):
   ```sql
   CREATE DATABASE cycle_todo;
   CREATE USER cycle_todo WITH PASSWORD '<generated-strong-password>';
   GRANT ALL PRIVILEGES ON DATABASE cycle_todo TO cycle_todo;
   ```

2. **Create the env file** at e.g. `/opt/markcheli/tasks.env`. Use `openssl rand -hex 32` for the JWT secret. Leave Google vars blank for now.

3. **Pull and run:**
   ```bash
   docker compose pull tasks
   docker compose up -d tasks
   docker compose logs -f tasks   # confirm: alembic ran, server started, no errors
   ```

4. **Verify health:**
   ```bash
   curl http://localhost:8000/api/health     # {"status":"ok"}
   curl http://localhost:8000/api/health/db  # {"status":"ok","db":"ok"}
   ```

5. **Configure NGINX** for `tasks.markcheli.com` → `127.0.0.1:8000`. Reload.

6. **Smoke test:**
   - Visit `https://tasks.markcheli.com` — login page renders.
   - Log in with the test user. Land on `/cycle`.
   - Add a task. Reload. Confirm persistence.

## Updates

```bash
docker compose pull tasks
docker compose up -d tasks
```

Migrations run on each startup. Downtime ~5 seconds.

## Rollback

```bash
docker pull ghcr.io/mcheli/tasks:<previous-sha>
docker tag ghcr.io/mcheli/tasks:<previous-sha> ghcr.io/mcheli/tasks:latest
docker compose up -d tasks
```

If a rollback would require a schema downgrade, run Alembic manually first. (App migrations should always be forward-compatible.)

## Observability

- **Logs:** stdout/stderr. Forward to Fluent Bit → OpenSearch with the existing pipeline if desired.
- **Metrics:** none built into v1.
- **Health:** `/api/health` for liveness; `/api/health/db` for readiness (verifies DB connectivity).

## Known quirks / operational notes

- The image runs migrations on every start. If two replicas start simultaneously, alembic's transactional DDL serializes — safe but noisy in logs.
- The cycle uniqueness constraint (one active cycle per user+category) is enforced as a partial unique index. This is correct but means parallel cycle-create requests for the same user+category would fail one of them — not a real concern for a single-user app.
- The container expects the DB to be reachable within 60 seconds of startup. Past that, the entrypoint exits non-zero and the orchestrator restarts.
- Google OAuth routes return `503 not configured` until both `TASKS_GOOGLE_CLIENT_ID` and `TASKS_GOOGLE_CLIENT_SECRET` are set. The frontend's "Sign in with Google" button is disabled with a tooltip until then.

## Post-deploy tasks (Mark)

1. Complete Google OAuth setup in Google Cloud Console:
   - Create project "Tasks".
   - APIs & Services → OAuth consent screen → External; add Mark as a test user.
   - APIs & Services → Credentials → OAuth 2.0 Client ID → Web application.
   - Authorized redirect URIs: `https://tasks.markcheli.com/api/auth/google/callback` (and `http://localhost:8001/api/auth/google/callback` if testing locally).
   - Set `TASKS_GOOGLE_CLIENT_ID`, `TASKS_GOOGLE_CLIENT_SECRET`, `TASKS_GOOGLE_REDIRECT_URI`. Restart the container.
2. Optional: set up `pg_dump` cron on the DB host.
3. Optional: rotate the test user password by running a SQL update against `users.hashed_password` (no UI for this in v1).

---

*Last updated: 2026-04-19 by implementation agent.*

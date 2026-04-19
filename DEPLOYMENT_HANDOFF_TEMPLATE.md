# Deployment Handoff Template

> **Instructions for the implementation agent:** As you build, keep this file updated with every environment variable, port, volume, and runtime dependency the deployment agent will need. By the time the repo is ready for deployment, this file should be complete and self-contained — the deployment agent should not need to read any other file in this repo.
>
> Commit this file to the repo root. When it's ready for production, copy its contents and hand to the deployment agent.

---

# Cycle Todo — Deployment Handoff

## What This App Is

A self-hosted, single-user todo application with cycle-based task management. Runs as a single Docker container; requires an external PostgreSQL 15+ database.

## Target Environment

- **Domain:** `tasks.markcheli.com`
- **Host:** Mark's Dell PowerEdge R630, Ubuntu 24.04
- **Reverse proxy:** NGINX (already configured on the host for other services)
- **TLS:** Let's Encrypt or Cloudflare Origin Certs (deployment agent's choice, consistent with existing homelab pattern)
- **Container runtime:** Docker + Docker Compose (existing on the host)

## Container Image

- **Registry:** GitHub Container Registry (GHCR)
- **Image:** `ghcr.io/mcheli/cycle-todo`
- **Tags:** `latest` (main branch), `:{sha}` (every commit), `:v{version}` (tagged releases)
- **Port:** exposes `8000` (HTTP) internally. Behind NGINX.
- **Healthcheck:** `GET /api/health` returns `{"status":"ok"}` with 200.
- **User:** Container runs as non-root (uid 1000). No special capabilities needed.

## Database

- **Engine:** PostgreSQL 15 or newer.
- **Required:** A dedicated database + user for this app. Recommended: database `cycle_todo`, user `cycle_todo`.
- **Network:** Container must be able to reach the DB host on port 5432.
- **Initial setup:** Container runs `alembic upgrade head` on startup. No manual SQL needed. Safe to re-run.
- **Backups:** Daily `pg_dump` to Mark's NAS is recommended. Not handled by this app.

## Environment Variables

Required for the container to start cleanly:

| Variable | Required | Description | Example |
|---|---|---|---|
| `ENV` | yes | `production` | `production` |
| `ENABLE_DOCS` | no | Set to `false` to hide `/api/docs` | `false` |
| `DATABASE_URL` | yes | Full async Postgres URL. Must use `postgresql+asyncpg://` | `postgresql+asyncpg://cycle_todo:SECRET@db.internal:5432/cycle_todo` |
| `JWT_SECRET` | yes | 32+ byte random hex. Generate: `openssl rand -hex 32` | (64 hex chars) |
| `JWT_ALGORITHM` | no | Default `HS256`. Leave as-is. | `HS256` |
| `JWT_EXPIRE_DAYS` | no | Session lifetime. Default 7. | `7` |
| `COOKIE_SECURE` | yes | **Must be `true` in prod.** | `true` |
| `COOKIE_DOMAIN` | no | Leave blank unless Mark wants cross-subdomain sessions. | `` |
| `TEST_USER_EMAIL` | yes (for now) | Fallback login identity. Seeded on first startup if user doesn't exist. | `claudius@markcheli.com` |
| `TEST_USER_PASSWORD` | yes (for now) | Paired password. Same value as in `~/repos/tallied/.env`. | `<from Mark>` |
| `GOOGLE_CLIENT_ID` | no | Google OAuth. Leave blank until Mark completes Google Cloud Console setup. | `123.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | no | | `GOCSPX-...` |
| `GOOGLE_REDIRECT_URI` | no | Must match exactly what's configured in Google Cloud Console. | `https://tasks.markcheli.com/api/auth/google/callback` |
| `ALLOWED_ORIGINS` | yes | Comma-separated. Production should be the exact prod URL. | `https://tasks.markcheli.com` |

**Security:** `JWT_SECRET`, `DATABASE_URL`, `TEST_USER_PASSWORD`, `GOOGLE_CLIENT_SECRET` are secrets. Store in the deployment agent's secret manager; never commit.

## Sample `docker-compose.yml` for Production

(Deployment agent can adapt this to Mark's existing compose structure.)

```yaml
services:
  cycle-todo:
    image: ghcr.io/mcheli/cycle-todo:latest
    restart: unless-stopped
    env_file: /path/to/cycle-todo.env
    ports:
      - "127.0.0.1:8000:8000"   # bind to localhost; NGINX proxies in
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    depends_on:
      - postgres
    networks:
      - homelab

  # If not already running elsewhere:
  postgres:
    image: postgres:15
    restart: unless-stopped
    environment:
      POSTGRES_DB: cycle_todo
      POSTGRES_USER: cycle_todo
      POSTGRES_PASSWORD: ${CYCLE_TODO_DB_PASSWORD}
    volumes:
      - cycle_todo_pg:/var/lib/postgresql/data
    networks:
      - homelab

networks:
  homelab:
    external: true

volumes:
  cycle_todo_pg:
```

## NGINX Config (example — adapt to existing pattern)

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

## Volumes / Persistent State

The **container itself has no persistent state**. All state lives in PostgreSQL. The container can be destroyed and recreated freely; no volumes needed on the app container.

## Deployment Steps

1. **Create the database** (if not sharing an existing PG instance):
   ```sql
   CREATE DATABASE cycle_todo;
   CREATE USER cycle_todo WITH PASSWORD '<generated-strong-password>';
   GRANT ALL PRIVILEGES ON DATABASE cycle_todo TO cycle_todo;
   ```

2. **Create the env file** at e.g. `/opt/markcheli/cycle-todo.env` with the variables above.

3. **Pull and run:**
   ```bash
   docker compose pull cycle-todo
   docker compose up -d cycle-todo
   docker compose logs -f cycle-todo   # verify startup, alembic migration, no errors
   ```

4. **Verify:**
   ```bash
   curl http://localhost:8000/api/health    # {"status":"ok"}
   curl http://localhost:8000/api/health/db # {"status":"ok","db":"ok"}
   ```

5. **Configure NGINX** for `tasks.markcheli.com` → `127.0.0.1:8000`. Reload NGINX.

6. **Test the deployment:**
   - Visit `https://tasks.markcheli.com` — should show the login page.
   - Log in with the test user credentials.
   - Create a task. Reload. Confirm it persisted.

## Updating

```bash
docker compose pull cycle-todo
docker compose up -d cycle-todo
```

Migrations run automatically on startup. Downtime ~5 seconds.

## Rolling Back

```bash
# Roll to a specific SHA
docker pull ghcr.io/mcheli/cycle-todo:<sha>
docker tag ghcr.io/mcheli/cycle-todo:<sha> ghcr.io/mcheli/cycle-todo:latest
docker compose up -d cycle-todo
```

If the rollback includes a schema downgrade, run Alembic manually first (rare — the app's migrations should always be forward-compatible).

## Observability

- **Logs:** stdout/stderr (JSON-structured in prod). Deployment agent should forward to existing Fluent Bit → OpenSearch pipeline if desired.
- **Metrics:** Not built into v1. If needed, the deployment agent can add Prometheus via a sidecar or add instrumentation later.
- **Health:** `/api/health` for liveness, `/api/health/db` for readiness.

## Known Quirks & Operational Notes

*(Implementation agent: append to this list as you build. Any behavior the deployment agent might be surprised by goes here.)*

- None yet.

## Post-Deploy Tasks (Mark will do)

1. Complete Google OAuth setup in Google Cloud Console. Add the two env vars. Restart container.
2. Optionally: add a secondary user or change the test user's password via a SQL update (no UI for this in v1).
3. Set up `pg_dump` cron on the DB host.

---

*Last updated: [date] by [agent / Mark]*

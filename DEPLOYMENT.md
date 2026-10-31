# Tasks — Deployment

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

- **Registry:** GitHub Container Registry (GHCR), public (no auth needed to pull)
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
| `TASKS_JWT_SECRET` | yes | 32+ byte random hex. Generate: `openssl rand -hex 32`. With `TASKS_ENV=production` the app logs an ERROR at startup on the in-repo default (fail-closed is planned once prod is confirmed). | (64 hex chars) |
| `TASKS_API_KEY_PEPPER` | yes (prod) | HMAC pepper for stored API key hashes. `openssl rand -hex 32`. Changing it invalidates every existing API key. Production logs a warning while it is the default. | (64 hex chars) |
| `TASKS_JWT_ALGORITHM` | no | Default `HS256`. Leave as-is. | `HS256` |
| `TASKS_JWT_EXPIRE_DAYS` | no | Session lifetime. Default `7`. | `7` |
| `TASKS_COOKIE_SECURE` | yes (prod) | **Must be `true` behind HTTPS.** | `true` |
| `TASKS_COOKIE_DOMAIN` | no | Leave blank unless cross-subdomain SSO is wanted. | _(empty)_ |
| `TASKS_TEST_USER_EMAIL` | no (fallback) | Optional fallback login identity. Seeded on first startup if both are set. The password form is hidden in the UI whenever Google OAuth is configured, so this only matters when Google is NOT set. | `claudius@markcheli.com` |
| `TASKS_TEST_USER_PASSWORD` | no (fallback) | Paired password. Same caveat — only used when Google isn't set. | _(from Mark)_ |
| `TASKS_GOOGLE_CLIENT_ID` | yes (prod) | Google OAuth client ID. Mark has already created the OAuth app; he'll provide the rotated value. | `123.apps.googleusercontent.com` |
| `TASKS_GOOGLE_CLIENT_SECRET` | yes (prod) | Paired Google OAuth secret. | `GOCSPX-...` |
| `TASKS_GOOGLE_REDIRECT_URI` | yes (prod) | Must match exactly one of the redirect URIs registered in Google Cloud Console. | `https://tasks.markcheli.com/api/auth/google/callback` |
| `TASKS_ALLOWED_ORIGINS` | yes | Comma-separated list. Production should be the exact prod URL. | `https://tasks.markcheli.com` |
| `TASKS_DEMO_URL` | no | Real deployment: the public demo's URL; the login page shows a "Try the live demo" card. | `https://tasks-demo.markcheli.com` |
| `TASKS_DEMO_MODE` | demo only | `true` makes this deployment the read-only public demo. Never set on the real one. | `true` |
| `TASKS_DEMO_USER_EMAIL` | no | Demo persona. Must end in `@tasks.dev`. Default `claudius@tasks.dev`. | _(default)_ |
| `TASKS_STATIC_DIR` | no | Override the static-files location (defaults to `/app/static`). | _(empty)_ |

**Secrets:** `TASKS_JWT_SECRET`, `TASKS_API_KEY_PEPPER`, `TASKS_DATABASE_URL`, `TASKS_GOOGLE_CLIENT_SECRET` (and `TASKS_TEST_USER_PASSWORD` if used). Pull from the deployment agent's secret manager. Never commit to a repo.

### Sample env file

```dotenv
# /opt/markcheli/tasks.env
TASKS_ENV=production
TASKS_ENABLE_DOCS=false
TASKS_DATABASE_URL=postgresql+asyncpg://cycle_todo:DB_PASSWORD@db.internal:5432/cycle_todo
TASKS_JWT_SECRET=<openssl rand -hex 32>
TASKS_API_KEY_PEPPER=<openssl rand -hex 32>
TASKS_COOKIE_SECURE=true
TASKS_ALLOWED_ORIGINS=https://tasks.markcheli.com

TASKS_GOOGLE_CLIENT_ID=<from Mark>
TASKS_GOOGLE_CLIENT_SECRET=<from Mark>
TASKS_GOOGLE_REDIRECT_URI=https://tasks.markcheli.com/api/auth/google/callback

# Optional fallback (only used if Google vars are blank):
# TASKS_TEST_USER_EMAIL=
# TASKS_TEST_USER_PASSWORD=
```

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

2. **Create the env file** at e.g. `/opt/markcheli/tasks.env` using the sample above. Generate `TASKS_JWT_SECRET` with `openssl rand -hex 32`. Get the Google credentials from Mark (he'll have rotated them post-development).

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
   - Visit `https://tasks.markcheli.com` — login page renders showing only the "Continue with Google" button (because Google is configured).
   - Click it. Authenticate with Mark's Google account. Land on `/cycle`.
   - Add a task. Reload. Confirm persistence.
   - If anything's wrong: `docker compose logs tasks` and look for warnings around `Authlib`, `OAuth`, or `seed`.

## Updates

```bash
docker compose pull tasks
docker compose up -d tasks
```

Migrations run on each startup. Downtime ~5 seconds.

## Public demo (tasks-demo.markcheli.com)

The same image in demo mode, on its own database holding only the Claudius Banks seed. It must never share the real database, secrets or `.env`: startup refuses Google and test-user settings and any database with a user outside `@tasks.dev`.

| Container | Role |
|---|---|
| `tasks-demo-db` | `postgres:16-alpine`, volume `tasks_demo_db_data`, on the `tasks-demo` network (`internal: true`), no published port |
| `tasks-demo` | `ghcr.io/mcheli/tasks:latest` with `TASKS_DEMO_MODE=true`; on `tasks-demo` and `infrastructure` (for NGINX). The entrypoint runs migrations, then `python -m app.services.demo_seed --reset`, then the server. |

- **Environment** is listed in the compose file, never `env_file: .env`: `TASKS_DATABASE_URL` (the demo DB), `TASKS_JWT_SECRET` and `TASKS_API_KEY_PEPPER` (its own, from `TASKS_DEMO_*` in the server `.env`), `TASKS_ENV=production`, `TASKS_COOKIE_SECURE=true`, `TASKS_ALLOWED_ORIGINS=https://tasks-demo.markcheli.com`, `TASKS_DEMO_MODE=true`.
- **Fresh data:** the server crontab restarts `tasks-demo` at 08:30 UTC daily (Tallied's demo restarts at 08:00); the restart reseeds, and the site answers 502 for the few seconds that takes.
- **Real deployment:** `TASKS_DEMO_URL=https://tasks-demo.markcheli.com` on `tasks` shows the demo card on its login page.
- **NGINX:** a server block for `tasks-demo.markcheli.com` proxying to `tasks-demo:8000` with the wildcard certificate, plus the host in the port-80 redirect list. **DNS:** a proxied A record like `tasks`'s. (A flat name because the certificate covers one level.)
- **Deploy:** `~/83rr-poweredge/scripts/tasks-deploy.sh` pulls and restarts `tasks` and `tasks-demo` and checks both.
- **Check:** `curl -s https://tasks-demo.markcheli.com/api/auth/config` shows `"demo_mode":true`; a POST to `/api/api-keys` answers 403; `cd e2e && BASE=https://tasks-demo.markcheli.com node scripts/demo-tour.mjs` reports no problems.

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
- **Login UI behavior is reactive:** when both `TASKS_GOOGLE_CLIENT_ID` and `TASKS_GOOGLE_CLIENT_SECRET` are set, the login page shows ONLY a "Continue with Google" button and the password form is hidden. If those vars are missing, the page falls back to the email/password form and the Google routes return `503`. Restarting the container after toggling the env is required for the change to take effect.
- **Two cookies are set:** `session` (httpOnly JWT — the actual auth state) and `tasks_oauth_state` (Authlib's signed cookie for CSRF state during the Google round-trip; emptied after callback). Both use SameSite=Lax. NGINX must forward Set-Cookie verbatim (default behavior — no special config needed).
- **JWT secret is reused** for the OAuth state cookie's signing key. Rotating `TASKS_JWT_SECRET` invalidates both: existing user sessions and any in-flight OAuth redirects (those will fail their state check). Schedule rotation accordingly.
- bcrypt is pinned to `>=4.0,<4.1` because passlib 1.7.x reads `bcrypt.__about__` which 4.1+ removed. Don't bump bcrypt without checking passlib first.
- The Google "Test user" list in Google Cloud Console gates who can actually sign in. Until the OAuth app is "Verified" by Google (overkill for this), only listed test users (Mark's email) can authenticate. To add another user later, add them to that list in the Cloud Console.

## Post-deploy tasks (Mark)

1. Confirm the production redirect URI `https://tasks.markcheli.com/api/auth/google/callback` is in the OAuth client's "Authorized redirect URIs" list (it should already be — was added during initial setup).
2. Optional: set up `pg_dump` cron on the DB host.
3. Optional: add additional Google accounts to the OAuth consent screen "Test users" list if you want anyone else to be able to sign in.

---

*Last updated: 2026-04-19. Image `ghcr.io/mcheli/tasks:latest` is live and public on GHCR; CI + Release workflows green.*

# Deployment

This file is a pointer. The original spec content has been split out so each consumer reads exactly what they need:

| You are… | Read |
|---|---|
| The deployment agent | [`DEPLOYMENT_HANDOFF_TEMPLATE.md`](DEPLOYMENT_HANDOFF_TEMPLATE.md) — self-contained ops manual: image, env vars, sample env file, sample compose, NGINX, deploy steps, rollback, known quirks. |
| A developer working in this repo | [`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md#working-with-the-repo--key-commands) — section "Working with the Repo — Key Commands": local setup, dev servers, tests, lint, alembic, docker build, ports table. |
| A reader who wants the why | [`DECISIONS.md`](DECISIONS.md) — every judgment call (env prefix, image name, port shifts, schema fixes, etc.) with rationale. |
| Curious about the original architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md), [`API_SPEC.md`](API_SPEC.md), [`UI_FLOWS.md`](UI_FLOWS.md). These are the input spec — still accurate where DECISIONS.md doesn't override. |

## Quick reference

- **Image:** `ghcr.io/mcheli/tasks:latest` (also `:{sha}` and `:v{semver}`). Public on GHCR — pull without auth.
- **Internal port:** `8000`. NGINX proxies in.
- **Env var prefix:** `TASKS_`. Full table in the handoff doc.
- **CI:** `.github/workflows/ci.yml` runs lint + tests + docker-build on every PR and push to `main`.
- **Release:** `.github/workflows/release.yml` builds and pushes the image to GHCR on every push to `main` and on `v*` tags.
- **Health:** `GET /api/health` → 200, `GET /api/health/db` → 200.

## Why two docs?

`DEPLOYMENT_HANDOFF_TEMPLATE.md` is the operational doc — the deployment agent should not need to read anything else in this repo to deploy. `AGENT_INSTRUCTIONS.md` is the developer doc — has a much richer set of commands but assumes you have the source tree checked out. Keeping them separate avoids one of them drifting out of date because the audiences ask different questions.

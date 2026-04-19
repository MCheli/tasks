# Cycle Todo Application — Implementation Documentation

This documentation set defines a cycle-based todo application for Mark Cheli's homelab. It is intended to be loaded into a Claude Code session to drive implementation.

## Project Summary

A self-hosted todo application that organizes tasks into **planning cycles** (not a calendar-based weekly reset). Two independent buckets — **Personal** and **Professional** — share the same schema but run their own cycle lifecycles. Tasks carry a persistent identity across cycles, so push-forward history, task longevity, and a Gantt-style lineage visualization all come from the same source of truth.

## Document Index

Read in this order:

1. **`AGENT_INSTRUCTIONS.md`** — Start here. How the Claude Code agent should approach this build.
2. **`ARCHITECTURE.md`** — Tech stack, project structure, design principles.
3. **`DATABASE_SCHEMA.md`** — PostgreSQL schema, tables, indexes, migrations.
4. **`API_SPEC.md`** — Full REST API endpoint contract.
5. **`UI_FLOWS.md`** — Screen-by-screen UX flows and component hierarchy.
6. **`BACKEND_IMPLEMENTATION.md`** — FastAPI code patterns, service layer, auth.
7. **`FRONTEND_IMPLEMENTATION.md`** — Vue 3 components, state, routing, styling.
8. **`TESTING_STRATEGY.md`** — Unit, API, and end-to-end testing with Playwright MCP.
9. **`DEPLOYMENT.md`** — Self-contained ops manual for the deployment agent (image, env vars, sample compose, NGINX, deploy steps, known quirks).

## Core Requirements Summary

- **Cycles, not weeks.** A cycle is user-initiated, not calendar-bound. Each cycle has a start and end timestamp.
- **Two buckets.** Personal and Professional are independent — separate cycles, separate tabs, same schema.
- **Task lineage.** Tasks have a persistent ID (UUID). Each cycle holds its own row per task (status, position, notes), linked via `previous_task_id` to its predecessor. Push-forward count is derived, never stored.
- **Cycle transition workflow.** When a new cycle is initiated, all open tasks default to "move forward." The user can toggle each task between forward-arrow (carry), check (complete), or X (cancel). Hitting "Start Cycle" creates the new cycle and the carried-forward task rows.
- **Display ID.** Each task has a human-readable incrementing integer ID scoped per user (e.g. `#42`), so tasks can be referenced easily. Soft-deleted tasks leave gaps.
- **Soft delete.** Tasks are never removed; a `deleted_at` timestamp hides them from all views.
- **Reordering.** Drag-to-reorder any time. Position persists across cycle transitions.
- **History.** Gantt-style visualization with time on the X-axis, task lineages as horizontal bars, hover for details. Shows all tasks across all cycles.
- **Auth.** Google SSO for production; username/password for the test user. The implementation agent should build against the test user only and defer Google OAuth wiring until Mark sets up the Google Cloud Console project.

## Tech Stack

- **Backend:** FastAPI (Python 3.11+), SQLAlchemy 2.0 async, Alembic, Pydantic V2
- **Database:** PostgreSQL 15
- **Frontend:** Vue 3 (Composition API), Vite, Tailwind CSS, Pinia, Axios, Vue Router
- **Packaging:** Single Docker container (backend serves built frontend static files)
- **CI/CD:** GitHub Actions → GitHub Container Registry (GHCR)
- **Testing:** pytest, pytest-asyncio, httpx, Playwright MCP (for Claude-driven E2E)

## Reference Repo

The Tallied repo at `~/repos/tallied/` is a structural reference for FastAPI + PostgreSQL + Google SSO. The implementation agent should read that repo to align on patterns (project layout, auth scaffolding, Alembic setup, `.env` handling) before writing code.

## Deferred / Out of Scope (v1)

- Downstream integrations (Jira, Home Assistant to-do lists, AI task enrichment, iMessage, Telegram) — will be designed separately once core is deployed.
- Task sharing / multi-user collaboration — all data is user-scoped; no sharing.
- Native mobile app — web is styled mobile-first and that is sufficient.
- Notifications / reminders — out of scope.

## Production Domain

Deployment target subdomain: `tasks.markcheli.com`. The deployment agent handles NGINX, Let's Encrypt, and Cloudflare wiring — this repo just needs to produce a working container image and a filled-in `DEPLOYMENT.md`.

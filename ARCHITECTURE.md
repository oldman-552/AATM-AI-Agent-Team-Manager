# AATM Architecture

## Current status

This is the current Phase 1 architecture and a target boundary map, not a declaration that every planned component exists. The starting repository was a README-only skeleton.

## Principles

- Local-first and loopback-bound by default.
- Persist observable state in a relational database.
- Keep provider, orchestration, browser, project, and UI boundaries independent.
- Do not model provider behavior until its actual supported protocol is inspected.
- Render dashboard statistics from API/database state; use explicit loading/error/empty states.
- Treat destructive actions, paid calls, merges, and deployments as approval-gated operations.
- Avoid Redis, RabbitMQ, Docker, or distributed services without measured need.

## Current modules

1. **Web UI** — React + TypeScript + Vite, TanStack Query, i18next, relative typed API client. Current functional views: Dashboard, Projects, Agents, Tasks. English/Arabic/Persian initial resources; language selection persists; Arabic/Persian set `dir=rtl`.
2. **HTTP API** — FastAPI/Pydantic; versioned `/api/v1`; local default bind; configured Trusted Host and CORS middleware.
3. **Persistence** — SQLAlchemy 2.x and Alembic. Current records: projects, agent registrations, tasks, audit events. SQLite is the zero-setup default; a PostgreSQL URL can be configured with psycopg (not yet integration-tested).
4. **Progress tooling** — atomic status/log/state writer, secret-pattern redaction, and heartbeat/idle detection in `backend/app/progress.py` and `scripts/progress_reporter.py`.
5. **Setup scripts** — shell and PowerShell starter install/start/stop/update/uninstall scripts. Linux path is being exercised; Windows is pending.

## Planned components

- **Application services** — task orchestration, provider adapters, approval policy, audit, and project workflows isolated from HTTP handlers.
- **Provider adapters** — capability-oriented interface; Arena adapter only after inspecting Arena Local Bridge docs/protocol; Anthropic through its official SDK with explicit credential/budget authorization.
- **Browser manager** — Playwright persistent contexts, per-agent data directories, exclusive profile locks, and observable health.
- **Workspace/Git services** — isolated worktrees; protected merge/deploy boundaries.
- **Memory and QA** — project-isolated memory and independent, evidence-based review records.

## Current workflow boundary

The API persists projects, agent registrations, task metadata, and observable audit events. Creating or assigning a task does not execute it. The default Manager is an unconfigured identity, not an active model. Provider calls, task scheduling/execution, approvals, Git workflows, and browser sessions remain future work.

## Local process topology

For local development, Vite serves the UI and proxies relative `/api/v1` requests to FastAPI on `127.0.0.1`. Browser-facing code does not hardcode `localhost` for API calls. Hosted preview runs may bind Vite to `0.0.0.0` as required by the preview host; regular project scripts bind both services to loopback. Backend host validation remains restrictive.

# AATM — AI Agent Team Manager

AATM is a local-first AI engineering command center in early development. The complete product specification is preserved in [`AATM_MASTER_DEVELOPMENT_PROMPT.md`](AATM_MASTER_DEVELOPMENT_PROMPT.md). This repository began as a README-only skeleton; the foundation plus the provider-boundary and task-workflow slices described below are what exists today.

## Current verified foundation

- FastAPI API with a real database health check and database-backed dashboard counts.
- SQLAlchemy models and an Alembic initial migration for projects, agent registrations, tasks, and audit events.
- Local SQLite default, with a configurable SQLAlchemy database URL.
- A persisted, deliberately unconfigured Manager identity and 20 default worker-role templates.
- Project/agent/task record creation and listing; task assignment records; worker registration capped at 20.
- React + TypeScript + Vite UI for Dashboard, Projects, Agents, Tasks, Memory, Analytics, Approvals, and Providers, using a relative `/api/v1` path through the Vite proxy.
- English, Arabic, and Persian resources with 370 keys each, a key-parity/RTL unit test, a persisted selector, and `dir=rtl` for Arabic/Persian.
- Offline provider boundary: safe credential references, offline health, deterministic routing policies, and hard server-side budget enforcement — with **no** HTTP endpoint that performs a live model request.
- Task workflow state machine: validated transitions, dependency-gated ready queue, evidence requirements, replay-safe idempotency, and append-only history.
- Durable orchestrator: lease-based claims, bounded concurrency, backoff retries, crash recovery, and inspection/recovery endpoints — with execution disabled by default.
- Independent QA reviews (reviewer separation + concrete checks) and audited approval gates for paid/deploy/merge/delete operations (decisions recorded, actions not executed).
- Isolated local Git workspaces per project with branch creation and read-only status (no merge/push/fetch).
- Project-isolated memory with scoped entries, keyword retrieval, version history and export.
- Local CPU/memory/disk telemetry with an advisory (never auto-applied) concurrency recommendation.
- `scripts/backup.py` for consistent, verified, guarded SQLite backups and restores.
- Durable task checkpoints with an explicit resume plan (never "auto-resumed").
- Approval-gated pull-request plans that show the exact commands and never call the network.
- Delivery analytics computed only from stored rows, with explicit sample sizes and no synthetic scores.
- In-app notifications derived from real pending work, with server-side read state.
- Optional local bearer-token authentication plus CSRF-hardened mutations; the token is injected by the Vite proxy and never reaches the browser.
- Ubuntu shell and Windows PowerShell dependency/start/stop/update/uninstall entry points (Windows execution remains unverified here).
- Atomic progress event/status writer and a five-minute heartbeat command.

**Not implemented yet:** live provider traffic, real agent execution, orchestration over real executors, persistent browser profiles, memory, GitHub workflows, independent QA/recovery/approvals, confirmed billing reconciliation, backup/restore, and production authentication. Creating or moving a task record does not execute it; the Manager record does not make AI calls. Arena integration remains blocked pending a compliant supported route.

## Run locally

Prerequisites: Python 3.11+ and Node.js 20+ with npm. Docker is not required for the SQLite path.

Ubuntu/Linux:

```bash
scripts/install.sh
scripts/start.sh
# Open http://127.0.0.1:5173
scripts/stop.sh
```

Windows PowerShell:

```powershell
.\scripts\install.ps1
.\scripts\start.ps1
# Open http://127.0.0.1:5173
.\scripts\stop.ps1
```

The API binds to `127.0.0.1:8000` by default. The web development server also binds to loopback when started by these scripts; the Arena preview invocation explicitly overrides the web host so its preview can proxy requests. See [`INSTALLATION.md`](INSTALLATION.md).

## API and tests

- Health: `GET /api/v1/health`
- Providers (offline): `GET /api/v1/providers`, `GET /api/v1/providers/{id}/health`, `POST /api/v1/providers/route`
- Workflow: `GET /api/v1/tasks/workflow`, `GET /api/v1/tasks/ready`, `PATCH /api/v1/tasks/{id}/state`
- Quality: `GET|POST /api/v1/tasks/{id}/reviews`, `GET|POST /api/v1/approvals`
- Workspaces: `GET|POST|DELETE /api/v1/projects/{id}/workspace`, `POST .../workspace/branches`
- Memory: `GET|POST /api/v1/memory`, `GET /api/v1/memory/search`, `POST /api/v1/memory/{id}/rollback/{version}`
- System: `GET /api/v1/system/resources`
- Checkpoints: `GET|POST|DELETE /api/v1/tasks/{id}/checkpoints`, `GET /api/v1/tasks/{id}/resume-plan`
- Notifications: `GET /api/v1/notifications`, `POST /api/v1/notifications/read`, `POST /api/v1/notifications/read-all`
- Analytics: `GET /api/v1/analytics` (+ `/throughput`, `/cycle-time`, `/reviews`, `/rework`, `/approvals`, `/activity`)
- Pull-request plans: `GET|POST /api/v1/projects/{id}/pull-requests`, `POST .../{plan}/decision`, `POST .../{plan}/execute` (always refuses)
- Orchestrator: `GET /api/v1/orchestrator/status`, `POST /api/v1/orchestrator/recover`
- Dashboard: `GET /api/v1/dashboard`
- OpenAPI UI: `http://127.0.0.1:8000/docs`
- API routes and request examples: [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)

```bash
(cd backend && ../.venv/bin/python -m pytest)
(cd web && npm run build)
```

## Progress tracking

The required progress records are in the repository root: `STATUS.txt`, `PROGRESS_LOG.txt`, `IMPLEMENTATION_STATUS.md`, `BLOCKERS.txt`, and `NEXT_ACTIONS.txt`. To record significant activity atomically:

```bash
.venv/bin/python scripts/progress_reporter.py event \
  --phase 'Phase 1 — Foundation' --task 'Describe the task' \
  --action 'What was done' --activity 'What is happening now' \
  --tests 'Not run' --results 'Event recorded; no verification claimed'
```

For a 5-minute heartbeat while development is active, run `python scripts/progress_reporter.py heartbeat`. It marks stale activity idle and never claims work occurred just because a timestamp was updated. The heartbeat is a helper process; it is not left running automatically by the app.

## Status and security

- Latest development state: [`STATUS.txt`](STATUS.txt)
- Feature checklist: [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)
- Known limitations: [`BLOCKERS.txt`](BLOCKERS.txt)
- Configuration: [`CONFIGURATION.md`](CONFIGURATION.md)
- Security boundaries: [`SECURITY.md`](SECURITY.md)
- Test results: [`TESTING_REPORT.md`](TESTING_REPORT.md)

The application is not production-ready. Do not expose the API to an untrusted network. No API credentials are supported by the current foundation; never commit secrets or browser profiles.

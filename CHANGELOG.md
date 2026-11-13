# Changelog

## Unreleased — 2026-11-13

- Preserved the complete AATM master development prompt in `AATM_MASTER_DEVELOPMENT_PROMPT.md`.
- Added a local FastAPI/SQLAlchemy/Alembic foundation with SQLite defaults, health/dashboard routes, and project/agent/task/audit persistence.
- Added a default unconfigured Manager identity, 20 role templates, and a 20-worker registration cap.
- Added React/TypeScript/Vite Dashboard, Projects, Agents, and Tasks views with initial English, Arabic, and Persian resources.
- Added Ubuntu shell and Windows PowerShell starter setup/process/update/uninstall scripts.
- Added atomic progress events/status heartbeat tooling and initial architecture/security/API documentation.

### Added in the provider/workflow slice

- Offline provider boundary: contracts, credential references (`env:`/`keyring:`), configurable estimate pricing, hard budget guard, and deterministic routing with five policies.
- Provider API: catalog, per-provider offline health, safe configuration, routing settings, dry-run routing, budgets, and usage summary. No live-execution endpoint exists.
- Anthropic adapter using the official SDK, reachable only through an explicitly authorized in-process call with consent and budget checks; Arena adapter remains a hard-blocked stub.
- Task workflow service and API: validated transitions, dependency gating, ready queue, evidence requirements, retry counting, replay-safe idempotency keys, and append-only transition history.
- Alembic revision `0002_provider_boundary` (provider configs, budget limits, usage records, app settings, task transitions).
- Providers view in the UI plus per-task workflow actions; 216 translated keys in English, Arabic, and Persian.
- Durable orchestrator: lease-based claims, bounded concurrency, dependency-aware dispatch, exponential backoff with a retry ceiling, crash recovery for expired leases, and inspection/recovery endpoints. Execution is injected; the default executor refuses to run, so nothing is simulated.
- Alembic revision `0003_task_leases` (lease owner/expiry and next-attempt timestamp on tasks).
- Orchestrator panel in the Tasks view with lease/retry counts and an idempotent recovery action.
- Backend tests 9 → 44; Vitest resource tests added (5).

- Provider integrations beyond the gated Anthropic plumbing, real agent execution (no executor is configured), visual RTL verification, browser profiles, approval workflows, backup/restore, and Windows verification remain incomplete.

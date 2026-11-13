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
- Independent QA reviews with reviewer separation, concrete-check evidence, replay-safe verdicts, and a review form in the Tasks view.
- Approval gates for paid provider requests, protected merges, deployments and data deletion, with an Approvals view. Decisions are recorded and audited; the gated actions are never executed.
- Alembic revision `0004_reviews_approvals` (review records, approval requests).
- Isolated, local-only Git project workspaces: create from a local repository or fresh init, new work branches, read-only status/diff, root-escape protection, and audited removal. Merge/push/fetch/delete-branch are deliberately absent.
- Alembic revision `0005_project_workspaces`.
- Workspace panel in the Projects view.
- Optional local bearer-token authentication (`AATM_AUTH_MODE=token`) with constant-time comparison, fail-closed startup, and a Vite proxy that injects the token server-side so the browser bundle carries no secret.
- CSRF hardening: state-changing requests with a foreign `Origin` are rejected even when auth is off.
- Project-isolated memory with global/project/agent/task/decision scopes, deterministic keyword retrieval, version history with rollback-as-new-version, JSON export and audited deletion.
- Alembic revision `0006_memory`; Memory view with a project-scope selector.
- Local resource telemetry (CPU/memory/disk) with a bounded, explicitly advisory concurrency recommendation and a summary in the Tasks view.
- Local backup/restore CLI using SQLite's online backup API, with SHA-256 manifests, integrity verification, guarded restore that preserves the previous database, and retention pruning.
- Durable task checkpoints with monotonic sequences, a plain-language resume plan that never claims automatic resumption, credential rejection, and retention pruning; migration `0007_task_checkpoints`; `DELETE` added to CORS.
- Approval-gated pull-request plans with inert command previews, unsafe-input validation and an `execute` route that always refuses with a reason instead of fabricating success; migration `0008_github_plans`.
- Evidence-based analytics (counts, throughput, activity, cycle time with sample sizes, review approval rate, rework, approvals) with `null` for absent data and a naive timeline chart.
- Derived notifications (pending approvals, failed/rework tasks, expired leases) with persisted read state, mark-all, retention, a topbar bell and translated messages; migration `0009_notification_reads`.
- A real Settings page backed by validated, non-secret preferences (language, theme, page size, notification polling, retention) with reset, export and audit events.
- Deterministic Manager planning: rule-based findings, balanced assignment proposals, dependency ordering with cycle detection, and an explicit apply step that re-validates proposals and audits results.
- Agent lifecycle states with validated transitions, Manager protection, assignment refused for unavailable agents on both create and reassign, deny-by-default permission scopes (Manager-only `task:assign`), blocked-agent reporting and lifecycle/permission audit events; migration `0010_agent_permissions`.
- Fixed `scripts/start.sh` reporting a UI URL that was not serving: Vite now runs with `--strictPort` and the script verifies the UI responds before printing, exiting with guidance when the port is busy.
- Fixed a missing `save` translation that the new agent controls used; a Vitest guard now fails the build when any `t('key')` used in the UI is absent from English, Arabic or Persian.
- Browser profile registry with real isolated directories, exclusive locks, validated lifecycle, confirmation-gated deletion and a Browser Wall view that states automation is unavailable instead of faking it; migration `0011_browser_profiles`.
- Backend tests 9 → 137; Vitest tests 6.

- Provider integrations beyond the gated Anthropic plumbing, real agent execution (no executor is configured), visual RTL verification, browser profiles, backup/restore, authentication, and Windows verification remain incomplete. Approval gates record decisions but do not perform the gated operations.

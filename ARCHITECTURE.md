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

1. **Web UI** — React + TypeScript + Vite, TanStack Query, i18next, relative typed API client, and a vendor/app bundle split so framework code stays cacheable. Current functional views: Dashboard, Operations (audit log, usage/cost, resources), Projects, Project builder, Agents, Control center, Tasks (with workflow actions, review forms, resume points, execution timeline and cancellation), Memory, Analytics, Browsers, Approvals, Settings, Providers (offline configuration, routing dry run, budgets), and a per-project workspace panel. English/Arabic/Persian resources with 557 keys each and a Vitest parity test; language selection persists; Arabic/Persian set `dir=rtl`.
2. **HTTP API** — FastAPI/Pydantic; versioned `/api/v1`; local default bind; configured Trusted Host and CORS middleware; a 1 MB streamed body cap and hardening response headers (`backend/app/hardening.py`).
3. **Persistence** — SQLAlchemy 2.x and Alembic (revisions `0001_initial`, `0002_provider_boundary`, `0003_task_leases`, `0004_reviews_approvals`, `0005_project_workspaces`, `0006_memory`, `0007_task_checkpoints`, `0008_github_plans`, `0009_notification_reads`, `0010_agent_permissions`, `0011_browser_profiles`, `0012_task_cancellation`, `0013_agent_instructions`). Current records: projects, agent registrations, tasks, task transitions, audit events, provider configurations (references only), provider budget limits, usage records, and app settings, plus task lease/backoff columns. SQLite is the zero-setup default; a PostgreSQL URL can be configured with psycopg (not yet integration-tested).

4. **Provider boundary** (`backend/app/providers/`) — provider-agnostic contracts (`ProviderAdapter`, `ProviderHealth`, `CostEstimate`, `ProviderRequest`, `Authorization`), credential **references** (`env:`/`keyring:`), a configurable pricing/estimate table, a hard budget guard, and a deterministic routing engine with five policies. `ArenaBridgeAdapter` is a permanently blocked stub. `AnthropicAdapter` uses the official SDK but is reachable only through an explicitly authorized in-process call; no HTTP route exposes it, and `load_settings()` hard-codes `live_requests_allowed=False`.

5. **Orchestrator** (`backend/app/orchestrator.py`) — lease-based durable dispatch with bounded concurrency, exponential backoff, retry ceiling, and crash recovery. Execution itself is injected: the default executor refuses to run, and the HTTP surface exposes only status and recovery.

6. **Workflow service** (`backend/app/workflow.py`) — an explicit state machine with dependency gating (`completed`/`approved` satisfy dependencies), evidence requirements for failure/approval/rework, retry counting, and replay-safe idempotency keys backed by an append-only `task_transitions` table.
7. **Workspaces** (`backend/app/workspaces.py`) — isolated local Git repositories per project under a configurable root, with branch creation, read-only status/diff, strict path-escape protection, and a scrubbed non-interactive Git environment. Merges, pushes, fetches and deletions are not implemented.
8. **Memory** (`backend/app/memory.py`) — scoped, project-isolated knowledge with deterministic keyword retrieval, monotonic version history, rollback-as-new-version, export and audited deletion.
9. **Quality and approvals** (`backend/app/quality.py`) — reviewer separation, evidence-gated verdicts that drive the workflow, and approval gates that record decisions for paid/deploy/merge/delete operations without executing them.
10. **Browser profiles** (`backend/app/browser_profiles.py`) — per-profile isolated directories with validated lifecycle, exclusive locks and confirmation-gated deletion. No browser is launched, and cookie/login/session data is never read.
11. **Agent lifecycle and permissions** (`backend/app/agents.py`) — validated state machine, Manager protection, deny-by-default scopes with a Manager-only assignment scope, and assignment gates enforced on every path that can grant work.
12. **Manager planning** (`backend/app/planning.py`) — deterministic rules compute findings, balanced assignment proposals and dependency order; applying is explicit and re-validates each proposal. No model is called.
13. **Preferences** (`backend/app/app_settings.py`) — allow-listed, non-secret settings with strict validation, audit events and export; credential-shaped names are rejected by construction.
14. **Notifications** (`backend/app/notifications.py`) — items derived from pending approvals, failed/rework tasks and expired leases, with persisted read state and translation keys rather than server-side English.
15. **Analytics** (`backend/app/analytics.py`) — counts, throughput, activity, cycle time, review outcomes, rework and approvals computed only from persisted rows; absent data is `null`, never zeroed or estimated.
16. **Pull-request plans** (`backend/app/github_plans.py`) — recorded intent with a linked approval, inert command previews and no network access; `execute` refuses by design.
17. **Checkpoints** (`backend/app/checkpoints.py`) — append-only resume points with monotonic sequences, credential rejection and a resume plan that is explicitly advisory.
18. **Backup and restore** (`backend/app/backup.py`, `scripts/backup.py`) — online SQLite backup with SHA-256 manifests, verification before restore, preserved previous copies, and retention pruning.
19. **Resource telemetry** (`backend/app/resources.py`) — standard-library CPU/memory/disk sampling with a bounded advisory concurrency recommendation; nothing is uploaded and nothing is auto-applied.
20. **Progress tooling** — atomic status/log/state writer, secret-pattern redaction, and heartbeat/idle detection in `backend/app/progress.py` and `scripts/progress_reporter.py`.
21. **Setup scripts** — shell and PowerShell starter install/start/stop/update/uninstall scripts. Linux path is being exercised; Windows is pending.
22. **Execution timeline** (`backend/app/timeline.py`) — a read-only projection of transitions, checkpoints, task audits, reviews and approval requests; every entry names its `source` table, and nothing is inferred.
23. **Cooperative cancellation** (`backend/app/cancellation.py`) — intent is recorded first, honouring happens at a safe boundary, finished work is never rewritten, and the orchestrator applies pending cancellations before claiming.
24. **Agent control center** (`backend/app/agent_center.py`) — per-agent live state assembled from tasks, audit rows, usage records, leases and browser profiles, with an explicit `honesty` block; absent data is `null`.
25. **Self-healing and recovery** (`backend/app/recovery.py`) — classified database errors with rollback-before-close, bounded transient retry restricted to lock contention, queue health, and a capability table that marks only genuine automatic recoveries as automatic.
26. **Memory context** (`backend/app/memory_context.py`) — deterministic, budgeted context selection with an explicit exclusion list, and extractive summarization that never paraphrases.
27. **Local executor** (`backend/app/execution.py`) — bounded subprocess runner behind the `TaskExecutor` protocol; commands are named in `.aatm/exec.json`, allow-listed, shell-free, and opt-in via `AATM_EXECUTION_ENABLED`.
28. **Event stream** (`backend/app/events.py`) — SSE over a polled audit table, with a resumable keyset cursor and a bounded lifetime; the transport describes itself as polling.
29. **Team intelligence** (`backend/app/intelligence.py`) — complexity-weighted, sample-aware agent metrics with rule-based assessments kept in separate fields from the measurements.
30. **Project builder** (`backend/app/blueprints.py`) — a deterministic rule engine that turns a described idea into an eleven-section plan with provenance for every requirement; applying is explicit, re-validated and inert.

## Planned components

- **Application services** — real agent execution behind the executor boundary, approval policy, and project workflows isolated from HTTP handlers. The scheduler, concurrency bounds, retries and crash recovery now exist and are tested with fake executors.
- **Provider adapters** — the contract exists; Arena remains blocked until a compliant supported route is verified; Anthropic live execution stays gated behind explicit authorization, consent and budgets.
- **Browser manager** — Playwright persistent contexts, per-agent data directories, exclusive profile locks, and observable health.
- **Workspace/Git services** — isolated worktrees; protected merge/deploy boundaries.
- **Memory and QA** — project-isolated memory and independent, evidence-based review records.

## Current workflow boundary

The API persists projects, agent registrations, task metadata, validated task state transitions, provider configuration/health/budgets, and observable audit events.

Explicit non-claims:
- Creating, assigning, or moving a task **does not execute it**. The orchestrator can dispatch, but its default executor refuses to run, and no HTTP route can start a run.
- The default Manager is an unconfigured identity, not an active model.
- Provider health and routing are dry runs; no live model request is possible over HTTP.
- Approvals, Git workflows, browser sessions, memory, and recovery remain future work.

### Provider data flow (offline)

`ProviderConfig` (reference only) → `ProviderContext` (config + settings + budget guard + credential store) → adapter `health()`/`authorize()` → `RoutingEngine` decision. The only path to a real provider call is `AnthropicAdapter.execute()`, which requires an in-process caller, an explicit `live_execution_authorized` flag, a resolvable credential reference, explicit paid consent, and a passing budget check. Tests inject a fake SDK client.

## Local process topology

For local development, Vite serves the UI and proxies relative `/api/v1` requests to FastAPI on `127.0.0.1`. Browser-facing code does not hardcode `localhost` for API calls. Hosted preview runs may bind Vite to `0.0.0.0` as required by the preview host; regular project scripts bind both services to loopback. Backend host validation remains restrictive.

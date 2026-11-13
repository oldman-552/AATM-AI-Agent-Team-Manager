# Changelog

## Unreleased — 2026-11-13

- Preserved the complete AATM master development prompt in `AATM_MASTER_DEVELOPMENT_PROMPT.md`.
- Added a local FastAPI/SQLAlchemy/Alembic foundation with SQLite defaults, health/dashboard routes, and project/agent/task/audit persistence.
- Added a default unconfigured Manager identity, 20 role templates, and a 20-worker registration cap.
- Added React/TypeScript/Vite Dashboard, Projects, Agents, and Tasks views with initial English, Arabic, and Persian resources.
- Added Ubuntu shell and Windows PowerShell starter setup/process/update/uninstall scripts.
- Added atomic progress events/status heartbeat tooling and initial architecture/security/API documentation.

### Memory context selection and summarization (Part 9)

- `GET /api/v1/memory/context`: deterministic, budgeted context selection (relevance → scope priority → recency → title) with an explicit `excluded[]` list so a dropped requirement can never be silent.
- `GET /api/v1/memory/summarize/{id}`: **extractive** summaries only — sentences copied verbatim. The method is stated in the payload, and the budget reports `unit: "words"` rather than pretending to count provider tokens.
- A relevant entry that would overflow the budget is reduced to a verbatim extract before being excluded.
- Context selection panel in the Memory view with a budget bar, per-entry `full`/`extract` tags and the exclusion list; 597 keys × en/ar/fa.
- Backend tests 195 → 201.

### Self-healing and recovery slice

- `GET /api/v1/recovery`: an honest capability table (five detected, **two genuinely automatic**, two explicitly not applicable), a real database probe with a SQLite integrity check, and queue health.
- Database errors are classified instead of returning an opaque 500 (`locked`/`constraint` → 409, `schema`/`corrupt`/`unavailable` → 503) with actionable advice; `/health` degrades to `503` with the cause rather than raising.
- Request sessions now roll back before closing, so one failed transaction cannot poison the next request on a pooled connection. Transient retry is restricted to lock contention — an integrity error is never retried.
- **Fixed**: an oversized body behind a proxy returned 500 instead of 413, because the server replied and closed mid-upload. The body is now drained (bounded) before replying, verified through the Vite proxy.
- Recovery panel in Settings showing the capability table, queue health and integrity result; 583 keys × en/ar/fa.
- Backend tests 181 → 195.

### Permission levels completed to the specification (nine levels)

- The scope set grew from six to ten scopes covering all nine named levels: added `pull_request:plan`, `merge:approve`, `production:approve` and `external:approve`.
- `GET /agents/scopes` now returns the level table plus `enforced_at`, so each scope names the boundary that actually checks it; `approval_only` marks the three scopes that can only record an approval.
- Manager-reserved enforcement is checked **before** the grant, so a corrupted row cannot confer merge or production rights on a worker.
- `POST /planning/apply` now refuses to hand planned work to an agent that has not declared `task:write`, skipping with `agent_lacks_task_write_scope`.
- Permissions panel shows an "approval only" or "Manager only" tag per scope; 563 translated keys.
- Backend tests 178 → 181.

### Hardened in the reliability and performance slice

- **Request body cap**: mutating requests above 1,000,000 bytes return `413` before any handler runs, and the cap is enforced by counting streamed bytes, not by trusting `Content-Length` (proven at the ASGI layer with an understated header). A non-numeric `Content-Length` returns `400`.
- **Security headers** on every response, including middleware rejections: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`, a restrictive `Permissions-Policy`, and `default-src 'none'; frame-ancestors 'none'` CSP for the JSON API. Headers are never duplicated.
- **Fixed an N+1 query** in `project_timeline`: it called the per-task builder for every task, issuing five queries per row. It now reads each table once for the whole project. Measured on 120 tasks: **94.1 ms → 12.1 ms**.
- Added `tests/test_performance.py` (list/dashboard/timeline/blueprint ceilings with median timing) and `tests/test_hardening.py` (7 tests). Backend tests 173 → 178.
- Measured on this machine (median of 7, 120 tasks, 25 checkpoints): tasks list 5.6 ms, dashboard 5.2 ms, agents/center 17.1 ms, task timeline 6.0 ms, project timeline 12.1 ms, blueprint 5.0 ms.

### Fixed and hardened in the RTL verification slice

- **Arabic was rendering Latin digits.** `Intl` reports Latin digits for the bare `ar` locale in this ICU build, so Arabic dates and numbers looked like `13/11/2026` while Persian localized correctly. All formatting now goes through `web/src/format.ts`, which requests `ar-u-nu-arab`: Arabic shows `١٣/١١/٢٠٢٦` and `١٬٢٣٤٫٥`.
- **Three unlocalized formatters removed**: `ApprovalsView` used `toLocaleString()` with no locale (so an English browser showed English dates inside an Arabic UI), and `CheckpointPanel`/`NotificationCenter` had the same class of bug.
- **New RTL guard** (`web/scripts/check-rtl-css.mjs`, wired as `npm run check:rtl` and `npm run verify`): fails on physical `margin/padding/border-left|right`, `text-align: left|right`, and asymmetric `left`/`right` offsets, in both source and the built bundle. Symmetric `inset` shorthand expanded by Vite's minifier is recognised as direction-neutral. Proven to fail on a three-defect probe file.
- `src/rtl.test.ts` (7 tests) also asserts direction switching, Arabic-Indic digits, Persian Solar Hijri dates, that every Arabic/Persian value actually contains Arabic script, and that no component formats dates inline.
- Frontend tests 6 → 13; `@types/node` added for the checker.

### Added in the AI Project Builder slice

- `POST /api/v1/blueprints`: a described idea becomes an eleven-section plan (requirements, architecture, stack, database design, phases, task breakdown, assignment plan, dependencies, testing strategy, acceptance criteria, delivery plan). Generated by **deterministic keyword/scale rules**, with `model_called: false` and a `detection_evidence` map naming the keywords behind each requirement.
- `POST /api/v1/blueprints/apply`: creating real tasks requires `confirmed: true` (`409` otherwise); the plan is re-validated (unknown/duplicate/self dependencies → `422`) and tasks are created dependency-linked in `pending`/`assigned` with nothing executed.
- Project Builder view with a rule-provenance panel, full plan tables and an explicit confirmation checkbox; 557 translated keys in English, Arabic and Persian.
- Backend tests 153 → 166.

### Added in the Live Agent Control Center slice

- `GET /api/v1/agents/center` and `/agents/{id}/center`: real per-agent state — current task, latest audit activity, wall-clock execution time, estimated vs confirmed cost, lease, browser-profile count, provider/auth status, errors and recent history — plus a `honesty` block naming each source. Absent data is `null`, never guessed.
- `POST /agents/{id}/instructions` (recorded, `delivered:false` until a real executor consumes it) and `GET /agents/{id}/instructions`.
- `POST /agents/{id}/reassign`: guarded task handover (no Manager, no paused/disabled/offline target, no finished work, no leased running task) with a `task.reassigned` audit event.
- Alembic revision `0013_agent_instructions`.
- New "Control center" view showing recorded state, with the browser-automation control explicitly shown as unavailable; 511 translated keys in English, Arabic and Persian.
- Backend tests 144 → 153.

### Added in the timeline/cancellation slice

- **Execution timeline** (`GET /tasks/{id}/timeline`, `GET /projects/{id}/timeline`): a read-only projection assembled only from `task_transitions`, `task_checkpoints`, `audit_events`, `review_records` and `approval_requests`; every entry names its `source` table so the claim is auditable. Reports `total`, `truncated` and the contributing sources.
- **Cooperative cancellation**: `POST /tasks/{id}/cancel` records intent without touching state; `POST /tasks/{id}/cancel/apply` honours it at a safe boundary; `DELETE` withdraws. Finished work is never rewritten — applying a pending request to a `completed` task returns `already_finished` and keeps the outcome.
- The orchestrator honours pending cancellations **before** claiming, so cancelled work is never started; `RunReport` gained `cancelled[]`.
- The workflow now requires a reason for any `cancelled` transition and allows `reviewing → cancelled`.
- Alembic revision `0012_task_cancellation` (`cancel_requested_at`, `cancel_reason`).
- Tasks view: inline timeline panel and cancel controls (request → pending banner → apply/withdraw); 476 translated keys in English, Arabic and Persian.
- Backend tests 137 → 144.

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

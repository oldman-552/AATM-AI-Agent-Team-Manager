# Changelog

## Unreleased — 2026-11-13

### Reviewable task-worktree diffs (read-only)

- Added `GET /api/v1/projects/{project_id}/workspace/tasks/{task_id}/diff`, a project-scoped patch preview from the worktree's recorded base commit. Git diff output is capped at 256 KiB and the diff process at 15 seconds; external diff/textconv helpers are disabled.
- Untracked paths are previewed separately only when they are contained regular UTF-8 text files no larger than 32 KiB, with caps of 32 files, 128 KiB aggregate text, 64 KiB for path enumeration, and five seconds for that enumeration. Binary files, symlinks, non-regular/oversized files and unsafe paths never return file contents.
- Added a lazy-loaded preview to each project task in the Tasks UI, including per-file and aggregate truncation states, localized in English, Arabic and Persian. Opening the preview is the only time the UI requests patch text.
- The endpoint is read-only: it never changes, commits, merges or deletes task worktrees. Tests cover tracked and untracked text, per-file and aggregate output limits, binary/symlink omission, missing worktrees, cross-project isolation and invalid ownership metadata.
- Verification: 262 backend tests passed locally, one PostgreSQL-only test skipped; 21 frontend tests, TypeScript, production build, and RTL checks passed. Hosted CI run `43485091743` passed the backend, frontend, and PostgreSQL migration/lock jobs. One upstream Starlette/httpx deprecation warning remains.

### Review-gated local task-worktree integration

- Added `POST /api/v1/projects/{project_id}/workspace/tasks/{task_id}/integrate` as a distinct explicit operation; diff and status previews remain read-only.
- Independent review records now bind to the exact task-worktree HEAD SHA (migration `0015_review_worktree_head`). Integration requires the task to be approved and a matching approved review, preventing commits made after review from being integrated.
- Only clean committed descendants of the recorded base can fast-forward into a clean non-protected local project branch whose HEAD has not moved. The full textual diff must fit the preview cap; binary, symlink, submodule, truncated, stale, or dirty cases fail closed. Git hooks are disabled for the operation, task worktrees remain unchanged, and no remote operation occurs.
- Integration and project branch/deletion mutations share the database-backed orchestrator lock. The Tasks UI now provides a separate localized confirmation action only when the approved review SHA matches the displayed HEAD; stale/missing review or any uncommitted files keep the action unavailable or fail closed. Tests cover real fast-forward, review-SHA binding, post-review changes, binary and dirty-workspace rejection, idempotent retry, audit event, hook suppression, lock contention, and the confirmation UI.
- Local verification: 265 backend tests passed, one PostgreSQL-only test skipped; 22 frontend tests, TypeScript, production build and RTL checks passed. Focused workspace/review tests cover the approval SHA, stale post-review commits, safe fast-forward, dirty/binary rejection, idempotency, audit, hook suppression and database-lock contention. Hosted CI run `43491561041` passed backend tests, frontend verification, and PostgreSQL migration/lock smoke.

### Bounded adaptive and parallel task dispatch

- Added `AATM_MAX_CONCURRENCY` (bounded 1–20, default 1) and `AATM_ADAPTIVE_CONCURRENCY` (off by default). When enabled, local CPU/memory/disk telemetry can only reduce the per-run dispatch batch; existing running tasks are subtracted and a zero budget claims no task.
- Serialized orchestrator run requests in one API process, exposed the calculated cap in status/run responses, and showed adaptive mode in Operations.
- Bounded parallel execution now runs tasks from different projects in a thread pool when the cap exceeds one; same-project tasks are excluded from the same batch. Worker ORM sessions are isolated, and workflow/database writes plus periodic lease heartbeats stay on the orchestrator thread. Migration `0014_orchestrator_run_lock` adds an expiring database lock that serializes API run requests across processes sharing a database; this is not a distributed task-level worker semaphore. Added GitHub Actions jobs for backend, frontend, and a PostgreSQL migration/run-lock smoke test; all three jobs passed on PR revision `ef94f36`. Upgraded the actions to Node 24-compatible major versions; all three jobs passed on revisions `e3f8751` and `f52ed89`.
- Updated configuration/API/architecture/implementation docs. Locale resources now have **652 keys each**.
- Verification after bounded parallel execution: **261 backend tests passed, 1 PostgreSQL-only test skipped locally**, **20 frontend tests passed**, TypeScript/build/RTL verification passed; one upstream Starlette/httpx warning remains.

### Budget alerts and documentation accuracy

- Derived an in-app warning when persisted provider usage reaches **80%** of a positive daily, monthly, global, agent, project, or credential budget. Alert scope and period follow the stored usage records; estimate/confirmed billing basis is identified.
- The alert is strictly advisory: `BudgetGuard` remains the sole hard enforcement point, and a request is denied only when its estimate would exceed an applicable limit. Tests explicitly verify that an under-cap request remains allowed at the alert threshold.
- Added the alert message in English, Arabic and Persian; notifications remain derived and read-state persistent.
- Corrected stale implementation/API/status documentation, including the old disabled-executor claim, missing SSE stream, and 321/450 translation-key counts.
- Verification: **244 backend tests passed**, **20 frontend tests passed**, `npm run verify` passed; one upstream Starlette/httpx deprecation warning remains.

- Preserved the complete AATM master development prompt in `AATM_MASTER_DEVELOPMENT_PROMPT.md`.
- Added a local FastAPI/SQLAlchemy/Alembic foundation with SQLite defaults, health/dashboard routes, and project/agent/task/audit persistence.
- Added a default unconfigured Manager identity, 20 role templates, and a 20-worker registration cap.
- Added React/TypeScript/Vite Dashboard, Projects, Agents, and Tasks views with initial English, Arabic, and Persian resources.
- Added Ubuntu shell and Windows PowerShell starter setup/process/update/uninstall scripts.
- Added atomic progress events/status heartbeat tooling and initial architecture/security/API documentation.

### Real local task execution, opt-in (Part 12)

- `LocalProcessExecutor` runs one named, allow-listed command per task inside its isolated project workspace. **A task names a command; it never contains one** — the argv comes from `.aatm/exec.json` that a human committed, because reading a command string from the database would make every task title remote code execution.
- Off by default: `POST /orchestrator/run` returns 409 unless `AATM_EXECUTION_ENABLED` is set. The environment can narrow the program allow-list but never widen it.
- Safety rules each with a test: no shell, bare allow-listed `argv[0]`, contained cwd, sanitised environment (no `AATM_*`/provider keys), timeout with process-group kill, output cap, cooperative cancellation, shutdown teardown.
- **Two real bugs found and fixed**: (1) the orchestrator held a write transaction across the subprocess run, so an operator's cancel request failed with `database is locked` — fixed by committing the claim first, plus SQLite WAL; (2) `expire_on_commit=False` left `cancel_requested_at` stale, so a stopped task stayed `running` forever — fixed with an explicit refresh. Both would have shipped invisibly.
- Cancellation is now a distinct `ExecutionCancelled` path: a withdrawal is not evidence about the work, so it must not increment `retry_count` or be reported as a failure.
- Verified live over HTTP: task → `completed`, real command output recorded, lease released, audit events written. Backend tests 220 → 241.

### Server-sent event stream (Part 21 real-time requirement)

- `GET /api/v1/events/stream` streams audit events as they are recorded, with a **resumable `(created_at, id)` cursor**, bounded lifetime, heartbeat, bounded batches and its own database session.
- **Honest transport**: the build has no message broker, so the server polls the audit table and the `hello` frame says `delivery: "poll"` with a note. The UI label says "near-real-time" for the same reason.
- **Fixed while testing**: a cursor on `created_at` alone dropped one of two events sharing a timestamp; keyset pagination on `(created_at, id)` fixes it, with a test inserting three identical timestamps.
- Live panel in the Operations view resumes from the last id on reconnect and backs off on failure; Eventsource auto-reconnect is bypassed because it ignores our cursor.
- **Auth parity**: the stream requires the same bearer token as other endpoints and explicitly rejects a `?token=` query fallback. Backend tests 212 → 220; frontend 16 → 20; 646 translated keys ×3.

### UI render smoke test

- Added a **jsdom render test** that mounts the real application with mocked API responses, clicks through every navigation section, and asserts the main region keeps real content after each swap.
- **It catches what HTTP checks cannot.** A first version passed while a deliberately injected crash was live: React logs render errors to `console.error` and unmounts the subtree instead of throwing, and the click loop was silently re-testing the already-active Dashboard. The test now fails on React's render errors, skips the active entry, and asserts that the markup actually changed and that most sections were visited. Verified by injecting a throw and watching it fail.
- Frontend tests 13 → 16.

### Operations view and bundle splitting

- New **Operations** view consolidating three sections the specification lists but the UI did not expose: Logs & Audit (a filterable event log), Usage & Costs (with the honest note that an empty column means *no call was made*, not that calls were free), and the Resource Monitor (nullable ratios rendered as "—", with the concurrency recommendation labelled advisory).
- **Bundle split**: vendor code is now separated from application code (react 181 kB, data 87 kB, app 232 kB), so a UI edit no longer invalidates the framework cache and no chunk exceeds the 500 kB warning threshold. CSS 50.41 kB, all gzipped sizes under 56 kB.
- 638 translated keys × en/ar/fa.

### AI Team Intelligence Center (Part 13)

- `GET /api/v1/intelligence?days=90`: per-agent measured metrics — tasks, success rate, **complexity-weighted** points, rework, reviews received, median completion time and estimated cost.
- **Fairness enforced in data, not convention**: complexity weights (low 1 / normal 2 / high 4 / urgent 6); `success_rate` counts failures in the denominator and excludes cancellations, with the rule published in `success_rate_denominator`; `sample_sufficient` flags thin samples; empty metrics are `null`, never `0`; `method.ranking` is `"none"`.
- Rule-based `assessments[]` carry their `basis` threshold and a `caveat`, and `model_generated` is `false`.
- **Fixed while testing**: terminal failures were initially left out of the success denominator, which would have reported a perfect rate for an agent that only ever fails.
- Intelligence panel in the Analytics view separating measured figures from labelled assessments; 621 keys × en/ar/fa.
- Backend tests 201 → 212.

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

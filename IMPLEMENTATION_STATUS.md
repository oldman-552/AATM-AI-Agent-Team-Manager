# AATM Implementation Status

This checklist reports repository evidence, not the intended product vision. Feature states are limited to `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED`, `TESTED`, `VERIFIED`, and `BLOCKED`. `VERIFIED` is reserved for behavior or research that was actually inspected/tested. The project began as a README-only repository on 2026-11-13.

## Phase 1 — Foundation

- [x] Inspect repository, branch, and runtime — **VERIFIED** (clean README-only repository; Python 3.11/Node 22 available; Docker and Windows unavailable).
- [x] Preserve the user's master prompt in `AATM_MASTER_DEVELOPMENT_PROMPT.md` — **IMPLEMENTED** (reviewed; 1,505 lines cover the stated 14 phases).
- [ ] Architecture and module boundaries — **IN PROGRESS** (initial architecture documented; review ongoing).
- [ ] FastAPI backend and runtime configuration — **TESTED** (health/dashboard/project/agent/task/event routes; included in API tests and live smoke checks).
- [ ] SQLAlchemy models, SQLite bootstrap, and Alembic migration — **TESTED** (app startup migration and file-backed restart test pass).
- [ ] Project, agent, task, and audit-record APIs — **TESTED** (create/list, assignment, role catalog, worker cap; tests pass).
- [ ] React + TypeScript + Vite UI — **TESTED** for compile/bundle and query wiring (TypeScript check, Vitest resource tests, and production bundle pass; browser visual/E2E checks remain pending).
- [ ] Frontend-to-backend relative API proxy — **VERIFIED** (actual Vite proxy returned backend health/dashboard; preview host smoke check passed).
- [ ] English/Arabic/Persian resources, RTL direction and key parity — **TESTED** for resource correctness (652 keys per language in the current tree; `web/src/i18n.test.ts` asserts identical key sets, no empty values, Arabic/Persian as distinct languages, and RTL direction for `ar`/`fa`). Visual layout/RTL browser verification remains **NOT STARTED**.
- [ ] Loopback/host/CORS baseline — **TESTED** (middleware and loopback defaults exist; dedicated tests assert untrusted Host rejection at 400 and that a hostile origin receives no `access-control-allow-origin` header). Real multi-user authentication remains absent.
- [ ] Local setup scripts — **TESTED** for Linux install/start/stop smoke flow; Windows PowerShell and update/uninstall paths are **IMPLEMENTED** but not executed.
- [ ] Phase 1 regression suite/build — **TESTED** (current run: 261 backend tests pass and the PostgreSQL-only smoke test is skipped without its CI service; 20 frontend Vitest tests pass; TypeScript/Vite production build and RTL CSS checks pass; see `TESTING_REPORT.md`).

## Phase 2 — AI Providers

- [x] Inspect actual Arena Local Bridge repository/docs and record protocol/security findings — **VERIFIED** (upstream commit `403122cf575b82aa519cad7c81a4cfe7d224d474`; see `PROVIDER_RESEARCH.md`).
- [ ] Arena provider adapter and live health/chat test — **BLOCKED** (upstream browser/reCAPTCHA/anti-automation behavior conflicts with the explicit no-bypass rule; no account or live request used). The adapter that exists today is a **permanently blocked stub**: `health()` always reports `state="blocked"`, `authorize()` always denies, `execute()` raises `ProviderBlocked`, and `PATCH /api/v1/providers/arena_bridge/config` returns 409 for any enabling change.
- [x] Provider abstraction boundary (configuration, offline health, routing, budgets, usage) — **TESTED** (20 new backend tests across three modules; requires no network; see `backend/app/providers/`).
- [x] Safe credential **references** (`env:NAME`, `keyring:service/account`) with raw-key rejection — **TESTED** (references validated and rejected when malformed; the API rejects unknown fields such as `api_key`; no credential value is ever stored, logged, or returned; values are redacted from provider error text).
- [x] Provider configuration API and persistence — **TESTED** (configuration, routing settings, budget limits and usage are persisted via Alembic revision `0002_provider_boundary`).
- [x] Hard server-side budget enforcement — **TESTED** (paid requests are denied without per-request consent, denied when no positive limit applies, and denied when daily/monthly/agent/project/credential/global limits would be exceeded; `paid_consent` is never inferred).
- [x] Deterministic routing policies with dry-run decisions — **TESTED** (`arena_first`, `claude_first`, `manual`, `task_based`, `user_defined`; every rejected candidate records a reason; `execution_performed` is always false and no usage record is written).
- [ ] Official Anthropic SDK live chat integration — **IN PROGRESS / GATED** (adapter uses the official `anthropic` SDK and is exercised in tests only with an injected fake client; there is deliberately **no HTTP endpoint** that performs a live call, and the global live switch is hard-coded off in `load_settings()`. Real API-key use, live request verification and confirmed billing reconciliation remain **NOT STARTED**).
- [ ] Confirmed provider billing import/reconciliation — **NOT STARTED** (costs are explicitly labelled local estimates, `billing_status="estimated"`).
- [ ] Encrypted credential vault / OS keyring verification — **NOT STARTED** (`keyring:` references fail closed when no backend is available; not verified on Windows).
- [ ] Token counting via provider tokenizer — **NOT STARTED** (estimates use caller-supplied token counts).

## Phase 3 — Agent Management

- [ ] Manager agent execution/planning — **TESTED for deterministic planning**: rule-based findings, least-loaded assignment proposals, dependency ordering with cycle detection, and an apply step that re-validates every proposal and records a reason for skipped ones. **No model is called**; LLM-driven planning remains **NOT STARTED** and is gated on the provider consent surface.
- [ ] Up to 20 independently configured worker agents — **IN PROGRESS** (registration metadata and cap exist; lifecycle/provider execution not implemented).
- [ ] Default role templates and custom roles — **IMPLEMENTED** (20 templates; full localized role UX/management still pending).
- [ ] Agent lifecycle and granular permissions — **TESTED** for lifecycle and scopes: validated `idle/active/paused/disabled` transitions, the Manager identity protected from disabling, assignment refused for unavailable agents (enforced on both create and reassign), deny-by-default scopes with a Manager-only `task:assign`, blocked-agent reporting, and audit events. Per-project authorisation tied to a user identity remains **NOT STARTED**.

## Phase 4 — Browser Profiles

- [ ] Playwright persistent contexts — **NOT STARTED**: no browser driver is installed and AATM never launches a browser. The *storage* half is **TESTED** (isolated per-profile directories, exclusive locks, lifecycle, confirmation-gated deletion).
- [ ] Independent, locked manager/worker profiles — **TESTED for independent and exclusively locked profile directories**: a second lock is refused and names the holder; profiles can be assigned to a specific agent; deletion is refused while locked and requires explicit confirmation.
- [ ] Browser health/auth state and recovery — **NOT STARTED by design**: inspecting auth state would mean reading credentials, which AATM refuses to do. `session_state` is always `not_inspected` and is documented as such rather than faked.
- [ ] Real-time Browser Wall — **IN PROGRESS**: the wall shows real profile directories, sizes, lock state and per-profile controls, and states plainly that automation is unavailable. Live page thumbnails require a browser driver and remain **NOT STARTED**.

## Phase 5 — Orchestration

- [ ] Durable task records and execution — task metadata, dependencies, assignment, state history, audit events, lease-based orchestration, retries, recovery, cancellation and the opt-in local executor are **TESTED**. The default executor remains disabled; no model or provider call is made.
- [x] Explicit task state machine with validated transitions — **TESTED** (`backend/app/workflow.py`; transitions, terminal states, evidence requirements for failure/approval/rework, retry counting, and a server-owned transition map at `GET /api/v1/tasks/workflow`).
- [x] Dependency gating and ready queue — **TESTED** (`GET /api/v1/tasks/ready` returns assigned tasks with satisfied dependencies only; starting a task with incomplete dependencies is rejected with 409).
- [x] Transition idempotency and append-only history — **TESTED** (replaying an idempotency key does not duplicate transitions or audit events; conflicting reuse is rejected; history survives an application restart).
- [x] Dependency-aware bounded parallel dispatch — **TESTED** (`backend/app/orchestrator.py`; `max_concurrency` caps claims, a bounded thread pool runs tasks from different projects concurrently (same-project tasks share a workspace and are excluded from one batch), dependency-unsatisfied tasks are never claimed, and tests prove overlap with a barrier while database mutations remain on the main thread).
- [x] Lease-based ownership with crash recovery — **TESTED** (claims write `lease_owner`/`lease_expires_at`; `recover_expired_leases` returns interrupted tasks to the queue, records the failure, and refuses to steal an active lease; recovery survives a process restart).
- [x] Retry policy with exponential backoff and a retry ceiling — **TESTED** (failures schedule `next_attempt_at`; a task is not dispatched before its backoff elapses; retries stop at `max_retries`).
- [x] Orchestrator observability + recovery API — **TESTED** (`GET /api/v1/orchestrator/status`, `POST /api/v1/orchestrator/recover`; the run endpoint is separately gated by the opt-in execution flag).
- [ ] Real local task execution — **TESTED** (opt-in `LocalProcessExecutor`, real allow-listed shell-free subprocesses inside project workspaces; disabled by default, with timeout/output caps, cancellation, and graceful shutdown). This does not execute an AI agent or call a model/provider.
- [x] Cancellation propagation and graceful shutdown — **TESTED** (request/apply/withdraw protocol, cross-connection cancellation observed by the orchestrator, cancelled tasks are not charged retry attempts, live processes are stopped at shutdown).
- [ ] Manager planning/assignment/review loop — **IN PROGRESS / TESTED for planning and assignment**: proposals → explicit apply → independent review via the existing QA loop. Automatic iteration without an operator remains **NOT STARTED**.

## Phase 6 — Projects and Memory

- [ ] Basic project records — **TESTED** (create/list and persistence tests pass).
- [x] Isolated Git workspaces per project — **TESTED** with real throwaway repositories (create from a local source or fresh init, branch creation, read-only status, strict root-escape and branch-name validation, audited removal). Merge/push/fetch/branch-deletion are intentionally absent.
- [ ] Project Builder and delivery plan — **TESTED** (rule-generated, eleven-section project plan; explicit apply revalidates inputs; the response states that no model was called).
- [ ] Global/project/agent/task/decision memory — **TESTED** for isolation and scoping (project-bound memory never appears in another project's list, search, export or direct lookup; global entries are shared deliberately).
- [ ] Memory search, retrieval, summarization, versioning, export, cleanup — **TESTED** for deterministic keyword retrieval, versioning with rollback-as-new-version, JSON export, explicit deletion and audit events. Context summaries are extractive selections of stored sentences (never generated/paraphrased); model-based summarization remains gated and **NOT STARTED**.

## Phase 7 — GitHub and Workspaces

- [ ] GitHub integration — **IN PROGRESS / TESTED for planning and gating**: per-project pull-request plans, unsafe-input validation, duplicate detection, approval linkage and audit events. Live execution is deliberately **NOT IMPLEMENTED**: `POST .../execute` always returns 409 with a reason, no token is read and no network request is made. A real remote/token flow remains **NOT STARTED**.
- [x] Isolated branches/worktrees and project workspaces — **TESTED** (local-only Git workspaces; see Phase 6).
- [ ] Approval-gated pull request/merge workflow — **TESTED for pull-request plans**: the plan cannot advance to an "executed" state, and approval decisions are recorded and audit-logged without executing. Merge/branch-protection workflows remain **NOT STARTED**.

## Phase 8 — QA and Intelligence

- [ ] Independent QA/review records — **TESTED** (server-side reviewer separation: self-review is rejected; `approved` needs concrete checks plus recorded output; `rework_required` needs a summary; verdicts drive the workflow and are replay-safe, audited, and exposed in the task UI).
- [x] Automated quality/test workflows — **TESTED** locally and in GitHub Actions (261 backend tests passed locally with one PostgreSQL-only smoke skipped without the CI service; 20 frontend tests; TypeScript, production build and RTL checks passed. Backend, frontend and PostgreSQL migration/run-lock CI jobs passed on PR revision `f52ed89` using Node 24-compatible action majors. Full PostgreSQL application/backup coverage remains open).
- [ ] Evidence-based agent analytics — **TESTED** for delivery analytics and the AI Team Intelligence Center: counts, throughput, cycle time, review/rework measures and per-agent complexity-weighted metrics derive from stored rows, expose sample sizes, keep rule-based assessments separate from measurements, and use `null` for missing data.

## Phase 9 — Recovery and Approvals

- [ ] Recovery diagnostics/checkpoints/safe retries — **TESTED** for lease recovery (expired leases are reconciled after a simulated crash and after a process restart; retry scheduling honours exponential backoff and a retry ceiling; an active lease is never stolen) and for durable **checkpoints** (append-only, monotonic sequences, credential rejection, resume plan that never claims automatic resumption). Automatic replay of partial agent work remains **NOT STARTED** by design.
- [ ] Human approval center and complete audit trail — **IN PROGRESS** (approval requests and decisions are persisted, audited and exposed in a dedicated Approvals view; the gated actions themselves are not executed, and the audit trail still lacks authentication attribution).
- [x] Observable execution timeline and resumable audit stream — **TESTED** (task/project timelines cite source tables; SSE audit stream uses a resumable keyset cursor, bounded lifetime, heartbeat, separate DB session and honest poll-transport labelling).

## Phase 10 — Cost and Resources

- [ ] Server-side budgets, cost/usage tracking and alerts — **TESTED** for consent-gated positive/scoped hard limits and persisted usage. In-app notifications advise at 80% of a positive limit; this threshold does not change enforcement. Usage is explicitly estimated unless later reconciled; billing reconciliation remains **NOT STARTED**.
- [ ] CPU/RAM/disk/browser monitoring and adaptive concurrency — **TESTED for CPU/memory/disk** (local standard-library sampling, bounded advisory recommendation, visible in Operations). Browser-level monitoring remains **NOT STARTED**. Resource-adaptive dispatch is **TESTED as an explicit opt-in per-run batch cap**; it never raises the configured maximum. A bounded thread pool provides parallel task execution when the cap exceeds one; task execution uses isolated worker sessions while workflow mutations and periodic lease heartbeats stay on the orchestrator thread. Lease renewal is covered by an expiry/recovery regression test. Cross-process API run serialization is **TESTED** using a database-backed expiring lock; distributed worker scheduling and per-worktree isolation remain **NOT STARTED**.

## Phase 11 — Dashboard and Interface

- [ ] Basic API-backed dashboard and responsive shell — **TESTED** (real backend counts, loading/error/empty states; production build and API smoke passed).
- [ ] Notifications — **TESTED** for derived in-app notifications: pending approvals, failed/rework tasks, expired leases and 80%-of-budget advisories, with server-persisted read state, mark-all, retention and English/Arabic/Persian keys. Email/webhook/push delivery remains **NOT STARTED**.
- [ ] Product interface — **TESTED** for navigation across Dashboard, Operations, Projects, Project Builder, Agents, Agent Center, Tasks, Memory, Analytics, Browser Wall, Approvals, Providers and Settings; includes notification bell and validated preferences. The Browser Wall displays real stored profile data but no browser automation; Manager chat is **NOT STARTED**.
- [x] Live updates through an appropriate backend event mechanism — **TESTED** (resumable SSE audit stream with bounded polling transport; the UI labels its delivery honestly).

## Phase 12 — Internationalization

- [ ] English/Arabic/Persian product UI — **TESTED** for dictionary parity (652 keys each), persisted language selection, direction, locale-aware number/date formatting, RTL CSS invariants in source and production bundle, and frontend render smoke. Pixel-level browser layout and Playwright RTL E2E remain **NOT STARTED** because no display/Playwright environment is available.

## Phase 13 — Reliability and Security

- [ ] Input validation and local-host/CORS baseline — **TESTED** (Trusted Host rejects unknown hosts with 400; hostile origins receive no CORS allow header; provider schemas reject unknown fields and raw credentials; task/review/approval payloads are validated with length bounds).
- [ ] Authentication/authorization and granular permission enforcement — **IN PROGRESS / TESTED for the local baseline**: opt-in single-user bearer-token auth (constant-time comparison, fail-closed configuration, token never in the browser bundle), cross-origin mutation rejection, and dedicated tests. User accounts, roles, per-project permissions and audit attribution to a principal remain **NOT STARTED**.
- [ ] Backup/restore, crash recovery, performance tests — **TESTED for backup/restore and crash recovery**: verified SQLite backups with manifests and guarded restore (`scripts/backup.py`), expired-lease reconciliation after a simulated crash, and durable checkpoints. Performance/load testing and PostgreSQL backup remain **NOT STARTED**.
- [ ] Sensitive-data protection, complete auditability, secure credential vault — **NOT STARTED**.

## Phase 14 — Cross-Platform Delivery

- [ ] Ubuntu installation/startup/shutdown — **TESTED** (install/start/stop script path and local API/UI proxy smoke test pass).
- [ ] Ubuntu update/uninstall workflow — **IMPLEMENTED** (clean-tree/fast-forward update and generated-dependency uninstall scripts; not executed).
- [ ] Windows installation/startup/shutdown/update/uninstall — **BLOCKED** (scripts exist, but no Windows host is available for execution).
- [ ] Cross-platform test suite and release packaging — **NOT STARTED**.

## Progress reporting and documentation

- [x] Required status/log/checklist/blocker/next-action files — **IMPLEMENTED** and being maintained.
- [x] Atomic progress event writer, secret-pattern redaction, heartbeat, and idle detection — **TESTED** (unit tests pass; 300-second long-running loop is not currently left active).
- [ ] Required documentation set — **IMPLEMENTED** as initial docs; final completeness review remains.
- [x] Testing report based on executed tests — **IMPLEMENTED**; refreshed after final regression and startup checks.

## RTL visual verification — reclassified (2026-11-13)

Previously recorded as "unverified: visual RTL layout". It is now verified to the extent a headless environment allows, and explicitly not beyond that:

- **Verified programmatically**: no physical left/right CSS declarations exist in the source stylesheet or the built bundle (`npm run check:rtl`, which fails on injected defects); Arabic and Persian switch `dir` to `rtl`; Arabic uses Arabic-Indic digits; Persian uses the Solar Hijri calendar; every Arabic/Persian dictionary value contains Arabic script, so no key was left in English; no component formats a date or number without a locale.
- **Still unverified**: pixel-level appearance in a real browser (font shaping, line breaking, mixed-direction strings such as file paths inside RTL paragraphs). Playwright and a display are both unavailable here, so this is recorded as an environment limit rather than claimed as done.

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
- [ ] English/Arabic/Persian resources, RTL direction and key parity — **TESTED** for resource correctness (321 keys per language, `web/src/i18n.test.ts` asserts identical key sets, no empty values, Arabic/Persian as distinct languages, and RTL direction for `ar`/`fa`). Visual layout/RTL browser verification remains **NOT STARTED**.
- [ ] Loopback/host/CORS baseline — **TESTED** (middleware and loopback defaults exist; dedicated tests assert untrusted Host rejection at 400 and that a hostile origin receives no `access-control-allow-origin` header). Real multi-user authentication remains absent.
- [ ] Local setup scripts — **TESTED** for Linux install/start/stop smoke flow; Windows PowerShell and update/uninstall paths are **IMPLEMENTED** but not executed.
- [ ] Phase 1 regression suite/build — **TESTED** (final run: 9 backend tests pass; TypeScript/Vite production build, shell syntax, Python compilation, dependency checks, and npm audit pass).

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

- [ ] Manager agent execution/planning — **NOT STARTED** (only an unconfigured Manager identity record exists).
- [ ] Up to 20 independently configured worker agents — **IN PROGRESS** (registration metadata and cap exist; lifecycle/provider execution not implemented).
- [ ] Default role templates and custom roles — **IMPLEMENTED** (20 templates; full localized role UX/management still pending).
- [ ] Agent lifecycle and granular permissions — **NOT STARTED**.

## Phase 4 — Browser Profiles

- [ ] Playwright persistent contexts — **NOT STARTED**.
- [ ] Independent, locked manager/worker profiles — **NOT STARTED**.
- [ ] Browser health/auth state and recovery — **NOT STARTED**.
- [ ] Real-time Browser Wall — **NOT STARTED**.

## Phase 5 — Orchestration

- [ ] Durable task records — **IN PROGRESS** (persisted metadata, dependencies, assignment, state history and audit events; no scheduler/executor).
- [x] Explicit task state machine with validated transitions — **TESTED** (`backend/app/workflow.py`; transitions, terminal states, evidence requirements for failure/approval/rework, retry counting, and a server-owned transition map at `GET /api/v1/tasks/workflow`).
- [x] Dependency gating and ready queue — **TESTED** (`GET /api/v1/tasks/ready` returns assigned tasks with satisfied dependencies only; starting a task with incomplete dependencies is rejected with 409).
- [x] Transition idempotency and append-only history — **TESTED** (replaying an idempotency key does not duplicate transitions or audit events; conflicting reuse is rejected; history survives an application restart).
- [x] Dependency-aware dispatch with bounded concurrency — **TESTED** (`backend/app/orchestrator.py`; `max_concurrency` caps dispatch, dependency-unsatisfied tasks are never claimed, and an injected fake executor is used in tests).
- [x] Lease-based ownership with crash recovery — **TESTED** (claims write `lease_owner`/`lease_expires_at`; `recover_expired_leases` returns interrupted tasks to the queue, records the failure, and refuses to steal an active lease; recovery survives a process restart).
- [x] Retry policy with exponential backoff and a retry ceiling — **TESTED** (failures schedule `next_attempt_at`; a task is not dispatched before its backoff elapses; retries stop at `max_retries`).
- [x] Orchestrator observability + idempotent recovery API — **TESTED** (`GET /api/v1/orchestrator/status`, `POST /api/v1/orchestrator/recover`; no dispatch endpoint exists).
- [ ] Real task execution by agents — **NOT STARTED** (the default `DisabledExecutor` refuses to run; nothing is simulated, and no provider/shell/browser work happens).
- [ ] Cancellation propagation and graceful shutdown — **NOT STARTED**.
- [ ] Manager planning/assignment/review loop — **NOT STARTED**.

## Phase 6 — Projects and Memory

- [ ] Basic project records — **TESTED** (create/list and persistence tests pass).
- [x] Isolated Git workspaces per project — **TESTED** with real throwaway repositories (create from a local source or fresh init, branch creation, read-only status, strict root-escape and branch-name validation, audited removal). Merge/push/fetch/branch-deletion are intentionally absent.
- [ ] Project Builder and delivery plan — **NOT STARTED**.
- [ ] Global/project/agent/task/decision memory — **TESTED** for isolation and scoping (project-bound memory never appears in another project's list, search, export or direct lookup; global entries are shared deliberately).
- [ ] Memory search, retrieval, summarization, versioning, export, cleanup — **IN PROGRESS / TESTED** for deterministic keyword retrieval, versioning with rollback-as-new-version, JSON export, explicit deletion and audit events. Summarization (which would require a provider) remains **NOT STARTED**.

## Phase 7 — GitHub and Workspaces

- [ ] GitHub integration — **NOT STARTED** (no remote, token or PR code exists).
- [x] Isolated branches/worktrees and project workspaces — **TESTED** (local-only Git workspaces; see Phase 6).
- [ ] Approval-gated pull request/merge workflow — **NOT STARTED**.

## Phase 8 — QA and Intelligence

- [ ] Independent QA/review records — **TESTED** (server-side reviewer separation: self-review is rejected; `approved` needs concrete checks plus recorded output; `rework_required` needs a summary; verdicts drive the workflow and are replay-safe, audited, and exposed in the task UI).
- [ ] Automated quality/test workflows — **IN PROGRESS** (backend suite: 51 tests; frontend Vitest resource tests; no CI pipeline yet).
- [ ] Evidence-based agent analytics — **NOT STARTED**.

## Phase 9 — Recovery and Approvals

- [ ] Recovery diagnostics/checkpoints/safe retries — **TESTED** for lease recovery (expired leases are reconciled after a simulated crash and after a process restart; retry scheduling honours exponential backoff and a retry ceiling; an active lease is never stolen) and for durable **checkpoints** (append-only, monotonic sequences, credential rejection, resume plan that never claims automatic resumption). Automatic replay of partial agent work remains **NOT STARTED** by design.
- [ ] Human approval center and complete audit trail — **IN PROGRESS** (approval requests and decisions are persisted, audited and exposed in a dedicated Approvals view; the gated actions themselves are not executed, and the audit trail still lacks authentication attribution).
- [ ] Observable execution timeline — **NOT STARTED**.

## Phase 10 — Cost and Resources

- [ ] Server-side budgets and cost/usage tracking — **TESTED** for enforcement plumbing (consent-gated, positive-limit-required, scoped limits; usage persisted and labelled as estimates; no confirmed billing reconciliation yet).
- [ ] CPU/RAM/disk/browser monitoring and adaptive concurrency — **TESTED for CPU/memory/disk** (local standard-library sampling, bounded advisory recommendation, visible in the Tasks view). Browser-level monitoring and automatic concurrency changes remain **NOT STARTED**.

## Phase 11 — Dashboard and Interface

- [ ] Basic API-backed dashboard and responsive shell — **TESTED** (real backend counts, loading/error/empty states; production build and API smoke passed).
- [ ] Complete navigation, manager chat, live control, Browser Wall, analytics, notifications, settings — **NOT STARTED**.
- [ ] Live updates through an appropriate backend event mechanism — **NOT STARTED** (dashboard polls current read APIs; no event stream).

## Phase 12 — Internationalization

- [ ] Complete English UI — **IN PROGRESS** (only initial four-view UI resources).
- [ ] Complete Arabic UI and verified RTL — **IN PROGRESS** (initial translations/direction; no browser RTL E2E verification).
- [ ] Complete Persian UI and verified RTL — **IN PROGRESS** (distinct initial translations/direction; no browser RTL E2E verification).
- [ ] Persisted immediate language switching and locale formatting — **IMPLEMENTED** (initial selector; cross-locale browser tests pending).

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

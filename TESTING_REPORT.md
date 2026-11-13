# Testing Report

## 2026-11-13 — Environment inspection

- Scope: Repository and runtime availability.
- Result: Clean README-only starting branch; Python 3.11.2, Node.js 22.22.3, npm 10.9.2 available. Docker unavailable; Windows host unavailable.

## 2026-11-13 12:57 UTC — Backend tests (current)

- Latest command: `cd backend && ../.venv/bin/python -m pytest`.
- Result: **137 passed, 1 warning** (128 new tests across this session).
- `tests/test_browser_profiles.py` (8 tests): a profile creates a real isolated directory under the configured root; no response claims automation and no credential field is exposed; names are validated and unique; locking is exclusive (second lock 409, deletion refused while locked, double-unlock 409); transitions are validated and `archived` is terminal; agent assignment is validated and detachable; deletion requires confirmation and reports removed bytes; size accounting reflects real files.
- `tests/test_agent_lifecycle.py` (6 tests): illegal jumps are 409 while legal ones work; paused agents cannot take new work on either assignment path while existing assignments are preserved; the Manager cannot be disabled or assigned; permissions start empty, unknown scopes are 422, duplicates collapse, and changes are audited; the Manager-only scope is refused even when granted; blocked agents are reported with their open-task count.
- `tests/test_planning.py` (7 tests): least-loaded proposals are balanced across agents and never auto-applied, with an explicit "no model was called" marker; dependency ordering respects blockers and blocked tasks are not proposed; already-assigned tasks are not re-proposed; applying writes assignments and audits both the assignment and the application; a stale plan is skipped (not forced) when someone assigned the task first; a plan without an id is 422 and unknown projects are 404; a plan retargeted at another project is refused.
- `tests/test_settings.py` (6 tests): defaults before any change; partial updates merge and persist across a restart; credential-named and unknown settings are rejected; value bounds enforced; reset and export work and the export contains no credential keys; changes are audited without storing secret values.
- `tests/test_notifications.py` (7 tests): an empty database produces no notifications; pending approvals become items and disappear once decided; read state survives an application restart; failed/rework tasks are reported with severity and target view; expired leases notify while live leases do not; malformed ids and retention bounds are rejected; `read-all` is idempotent.
- `tests/test_analytics.py` (4 tests): an empty database reports zero counts and `null` rates rather than invented numbers (with the seeded Manager identity accounted for); counts, throughput and cycle time follow real transitions; review approval rate and pending approvals are measured independently; rework share is computed and `days` bounds are enforced.
- `tests/test_github_plans.py` (7 tests): a plan is recorded with a linked `pull_request` approval; planned commands are inert text; `execute` always refuses with 409 and the plan stays `executed: false`; approval decisions mirror to `approved_not_executed`/`rejected` and repeats are 409; unsafe owner/repo/branch input and same-branch plans are 422; duplicate open plans are rejected but allowed again after rejection; plans are isolated per project and audited.
- `tests/test_checkpoints.py` (6 tests): monotonic, append-only checkpoint sequences; credential-shaped state/notes rejected (422) and nothing persisted; label/note/size/404 validation; the resume plan is guidance only (`resumed_automatically: false`) and distinguishes expired from live leases; retention keeps the newest checkpoints.
- `tests/test_backup.py` (8 tests): create → verify → mutate → restore round-trip against real SQLite files; restore refuses without `allow_overwrite`; path-traversal and oversized names rejected; duplicate names rejected; a tampered backup fails verification and its restore is refused; a missing database and a non-SQLite URL are rejected; pruning keeps the newest entries; a backup taken while the application holds an open connection is consistent.
- `tests/test_resources.py` (6 tests): recommendation bounded by the CPU ceiling rather than the configured max; memory/disk pressure force the floor; high load per core halves the recommendation; in-flight work is reported without changing configuration; the local sample returns plausible values with no network; the HTTP endpoint validates `configured_max` and never marks the recommendation as applied.
- `tests/test_memory.py` (6 tests): strict cross-project isolation for list/search/get/delete/rollback; deliberate global sharing with `include_global=false` opt-out; scope binding validation (project/agent/task requirements, unknown project, blank content); keyed versioning (v1 → v2 with the same id and `created: false`); rollback-as-new-version; version history; ranked keyword retrieval; blank-query rejection; JSON export; audit events.
- `tests/test_auth.py` (8 tests): token mode enforces bearer auth (health public, 401 with `WWW-Authenticate`); non-bearer/garbage schemes rejected; tokens never echoed; missing token configuration fails closed at startup; unknown mode falls back to `off`; cross-origin mutations are 403 even in `off` mode while same-origin and allow-listed origins work; cross-origin reads stay unauthenticated-CORS-denied; token mode still blocks hostile origins.
- `tests/test_workspaces.py` (7 tests): branch-name validation (`main`/`master`, traversal, `refs//head`, trailing slash rejected); workspace path cannot escape the root; a real local repository is cloned into an isolated workspace and its source stays clean; API lifecycle (create → duplicate 409 → branch creation → protected branch 422 → status → audited removal); unknown project/missing workspace; non-repository source rejected; cloning a local source preserves history and files.
- `tests/test_quality.py` (7 tests): self-review rejected; blank checks rejected; approval requires concrete checks and recorded output; replay returns `created: false`; verdict conflicts rejected; rework requires a summary and increments retries; unknown reviewer/task rejected; reviews before completion rejected; approval gates record decisions without executing anything; double decisions rejected; review and approval audit events written.
- `tests/test_orchestrator.py` (15 tests): default `DisabledExecutor` refuses to run and records a failure; fake executor completes a task with evidence and writes exactly the `assigned→running` / `running→completed` transitions; results without evidence are rejected; executor exceptions record only the exception type (so no secret can leak into the task record); `max_concurrency` caps dispatch; dependencies block dispatch until complete; expired leases are recovered then retried successfully; an active lease is never stolen; retry backoff and the retry ceiling behave; retries are not dispatched before backoff elapses; audit events are written; recovery works after an application restart; the orchestrator API is inspection/recovery only and `POST /orchestrator/run` does not exist; claims reject unassigned tasks and replay claims.
- Migration `0003_task_leases` verified: upgrade → columns present → downgrade to `0002_provider_boundary` → columns removed → re-upgrade → columns restored (file-backed SQLite).
- Migration `0004_reviews_approvals` verified the same way (upgrade → `review_records`/`approval_requests` present → downgrade to `0003_task_leases` → removed → re-upgrade → present).
- Migration `0005_project_workspaces` verified the same way (upgrade → table present → downgrade to `0004_reviews_approvals` → removed → re-upgrade → present).
- Migration `0011_browser_profiles` verified the same way (upgrade → `browser_profiles` present → downgrade to `0010_agent_permissions` → removed → re-upgrade → present, head `0011_browser_profiles`).
- Migration `0010_agent_permissions` verified the same way (upgrade → `agents.permissions` present → downgrade to `0009_notification_reads` → removed → re-upgrade → present, head `0010_agent_permissions`).
- Migration `0009_notification_reads` verified the same way (upgrade → `notification_reads` present → downgrade to `0008_github_plans` → removed → re-upgrade → present, head `0009_notification_reads`).
- Migration `0008_github_plans` verified the same way (upgrade → `github_pull_requests` present → downgrade to `0007_task_checkpoints` → removed → re-upgrade → present, head `0008_github_plans`).
- Migration `0007_task_checkpoints` verified the same way (upgrade → `task_checkpoints` present → downgrade to `0006_memory` → removed → re-upgrade → present, head `0007_task_checkpoints`).
- Migration `0006_memory` verified the same way (upgrade → `memory_entries`/`memory_versions` present → downgrade to `0005_project_workspaces` → removed → re-upgrade → present).
- New coverage this slice:
  - `tests/test_provider_boundary.py` (10 tests): credential-reference validation and secret redaction; configurable pricing marked as estimate-only; budget consent/no-limit/limit-exceeded/idempotent-commit behaviour; monthly and per-scope limits; Arena hard block; Claude execution gating (disabled without explicit authorization, produces no call without consent, records usage once on replay, blocks when the global switch is off); credential redaction in provider errors; routing that never selects a paid provider without consent and never records usage; deterministic policies; and a socket-blocking test proving health/routing open no sockets.
  - `tests/test_provider_api.py` (6 tests): catalog contains no secret values; raw credentials and unknown fields are rejected; references are accepted and clearable; Arena cannot be enabled (409); budgets plus dry-run routing with zero usage records; settings validation and absence of any execute route; untrusted Host and hostile Origin rejection.
  - `tests/test_workflow.py` (4 tests): validated transitions with audit + idempotent replay; invalid/conflicting transitions rejected; evidence requirement; retry counting; dependency gating and ready queue; terminal states; transitions persisting across an application restart.
- Previously reported (historical, same tree minus this slice): 9 passed, 1 warning.
- Coverage: health/database query and default manager seed; project/agent/task creation and dashboard counts; invalid project/dependency and assignment clearing; role catalog count; 20-worker cap; file-backed database persistence across app restarts and idempotent migrations; untrusted Host rejection; progress event history/atomic status update, secret-pattern redaction, and idle-heartbeat behavior.
- Warning: Installed Starlette emits `StarletteDeprecationWarning` because its `TestClient` still uses `httpx`; test assertions passed. This is a dependency ecosystem warning, not suppressed.

## 2026-11-13 12:57 UTC — Frontend tests and build (current)

- `cd web && npm test` (Vitest 2.1.9) → **6 passed**.
  - Asserts English/Arabic/Persian are the only supported languages, that all three key sets are identical (450 keys each), that no translation is empty, that Arabic and Persian are genuinely distinct translations (not copies), and that `ar`/`fa` are RTL while `en` is LTR.
- `cd web && npm run build` (`tsc --noEmit && vite build`) → **Passed**; 1662 modules, `dist/assets/index-C4Qz_Y5p.css` 39.99 kB, `dist/assets/index-C_LDMw1b.js` 413.68 kB.
- First TypeScript run failed twice: a missing `Send` icon import in `ProvidersView.tsx` and an invalid Vitest assertion overload in `i18n.test.ts`. Both were fixed before the passing run.

## 2026-11-13 — Frontend build (historical)

- Passed; TypeScript check and Vite 6.4.6 production bundle completed.
- Initial attempt: Failed on unused imports and an i18next interpolation type mismatch; those were fixed before the passing builds.

## 2026-11-13 — API/proxy smoke checks

- Direct backend checks: `GET /api/v1/health`, `/api/v1/dashboard`, `/api/v1/agent-roles`.
- UI/proxy checks: Vite root, `/api/v1/health`, and `/api/v1/dashboard`; preview-style Host `5173-arena-sandbox.e2b.app` was accepted and proxied.
- Result: Database health `ok`; actual dashboard counts returned 0 projects, 1 persisted unconfigured Manager, 0 tasks; role endpoint returned 20; proxy forwarded health/dashboard successfully.
- Migration: Application startup applied Alembic revision `0001_initial` to the configured local SQLite DB.

## 2026-11-13 — Setup and progress tooling

- `scripts/install.sh`: Ran successfully; Python/npm dependencies installed, including the PostgreSQL psycopg driver; npm reported 0 vulnerabilities.
- `scripts/start.sh`/`scripts/stop.sh`: Smoke-tested on alternate local ports; first attempt returned a Vite 404 because the frontend was launched from repository root. Fixed the working-directory bug; retest served the UI and proxied API successfully, then stopped the test processes.
- `.env` startup settings: Started with a temporary `.env` specifying backend port 8101 and a disposable SQLite path; the UI proxy reached that non-default API port. The first one-command check raced server startup and failed immediately; checking after startup in the following tool call passed. Temporary `.env` and database were removed.
- `bash -n scripts/*.sh`: Passed.
- Python `compileall`: Passed for application, migrations, tests, and reporter.
- `pip check`: Passed (`No broken requirements found`).
- `npm audit --audit-level=moderate`: Passed (0 vulnerabilities reported).
- Progress reporter CLI: event + one-shot heartbeat round trip passed on a temporary status/log directory; unit tests cover secret redaction and idle detection.

## 2026-11-13 12:50 UTC — Live local integration smoke test

- Backend run on `127.0.0.1:8000`, Vite on `0.0.0.0:5173` proxying `/api/v1`.
- `GET /api/v1/health` → `ok`; `GET /api/v1/providers` → both providers, Arena `blocked`, `live_requests_allowed: false`.
- `POST /api/v1/providers/route {"paid_consent": true}` → `no_eligible_provider` with explicit per-candidate reasons (Arena blocked; Claude disabled) and `execution_performed: false`.
- Full workflow over HTTP: created an agent and a task, `GET /tasks/ready` listed it, `PATCH /tasks/{id}/state` `assigned→running` returned `transition_created: true`, an identical replay returned `false`, `running→completed` with an evidence note succeeded, and `/api/v1/events` showed the two state changes.
- Preview-host check: request with `Host: 5173-<sandbox>.e2b.app` returned HTTP 200 and proxied API JSON, so the hosted preview path works through Vite.
- Cleanup: `.aatm-home` (git-ignored smoke database) only; no credentials, no provider traffic.
- Notable: binding uvicorn to `0.0.0.0` makes the API reject the preview Host with 400 (by design). Only Vite is exposed for previews; the API stays loopback-bound.
- Orchestrator endpoints were re-verified on a restarted server: startup applied migration `0003_task_leases`, `/api/v1/orchestrator/status` reported `executor.configured: false` with the refusal reason, and the same payload was served through the Vite proxy.
- Browser profiles verified live through the Vite proxy: a directory was really created under `.aatm-home/browser-profiles/<id>`, the second lock was refused naming `worker-a`, deletion while locked was refused, deletion without `confirm` was refused with 422, and the confirmed delete removed the directory from disk.
- Agent lifecycle verified live through the Vite proxy: `idle → paused` rejected with 409 and the allowed set listed, `active`/`paused` accepted, assignment to the paused agent refused with 409 `agent_paused`, an unknown scope refused with 422, and disabling the Manager refused with 409.
- Manager planning verified live through the Vite proxy: two unassigned tasks were proposed to two different agents, apply wrote both assignments, and both tasks moved to `assigned`.
- Preferences verified live through the Vite proxy: defaults returned, `{language: fa, theme: light, page_size: 50}` persisted and read back through a direct API call, `api_key` rejected with 422 `extra_forbidden`, and reset restored `en`/`dark`.
- Notifications verified live through the Vite proxy: an approval created two unread items, marking one read dropped unread to 1 and the state was visible through a direct API read, and deciding the approval removed its derived item.
- Analytics verified live through the Vite proxy against the real database: `{projects: 4, agents: 5, tasks: 3, active: 1, terminal: 2, checkpoints: 2}`, throughput 3, 30 audit events, cycle time with `samples: 2` and one explicitly excluded task, and `days=0`/`days=91` rejected with 422.
- Pull-request plans verified live through the Vite proxy: plan created as `awaiting_approval` with `executed: false`, `execute` refused with 409 and a clear reason, approval moved it to `approved_not_executed` while `executed` stayed false, and `repo: "../etc"` was rejected with 422.
- Checkpoints verified live through the Vite proxy: two checkpoints with sequences 1 and 2, a resume plan listing concrete next actions with `resumed_automatically: false`, a credential-shaped payload rejected with 422, and a `DELETE` preflight now advertising `DELETE`.
- Backup CLI verified end to end at `/tmp/bk`: create (282,624 bytes), `verify` → `sha256 matches manifest, integrity_check: ok`, restore refused without `--yes` (exit 2) and without `allow_overwrite` (exit 1), then a real restore that brought back a deleted project row and kept the replaced database as `db.pre-restore-20261113T131548Z.sqlite3`.
- Resource telemetry verified live through the Vite proxy: real CPU/memory/disk values, a bounded recommendation, and `applied_automatically: false`.
- Memory isolation verified live: versioned writes (v1→v2, same id), a global entry visible everywhere, Alpha's private entry absent from Beta's list and search, and the same payload served through the Vite proxy.
- Authentication verified live through the real Vite proxy: direct API without a token → 401; `/health` → 200; with token → 200; through the proxy with **no** browser token → 200 (proxy injects); a `grep` of `web/src` and `web/dist` found no occurrence of the token; preview-host proxying → 200; hostile-origin POST → 403.
- Review/approval flow re-verified live after restarting on migration `0004_reviews_approvals`: self-review returned 409; a check-free approval returned 409; an independent review with a concrete check moved the task to `approved`; an approval request was recorded then approved with the response stating the gated action is not executed; the approvals list was readable through the Vite proxy.

## 2026-11-13 — Provider research

- Inspected upstream Arena Local Bridge v1.1.0 at commit `403122cf575b82aa519cad7c81a4cfe7d224d474` from its public repository.
- Result: Actual local OpenAI-compatible protocol and bearer-key/session behavior documented in `PROVIDER_RESEARCH.md`. No live bridge or Arena account was used because the inspected source includes CAPTCHA token generation/anti-automation behavior that conflicts with the explicit no-bypass requirement.

## 2026-11-13 13:35 UTC — Full-stack regression pass

All read endpoints answered 200 through the real Vite proxy: `health, dashboard, projects, agents, tasks, approvals, providers, memory, analytics, notifications, settings, events, orchestrator/status, agent-roles, agents/scopes, agents/blocked, system/resources, settings/export, planning/proposals`.

One end-to-end flow exercised every slice in sequence on the same project:

| Step | Observed |
| --- | --- |
| Workspace create | local repo initialised; read-only status reported `main` and clean |
| Checkpoint | sequence 1 recorded |
| Memory write | keyed entry at version 1 |
| Workflow | `assigned → running → completed` |
| Self-review by the assignee | **409** "A task cannot be reviewed by the agent that is assigned to it." |
| Approval with no checks | **409** "Approval requires at least one concrete check with a result." |
| Approval without recorded output | **409** "Approval requires recorded task output as evidence." |
| Review by a different agent | verdict `approved`; task moved to `approved` |
| Review replay with the same idempotency key | `created: false`; state unchanged |
| Pull-request plan | `awaiting_approval`, `executed: false` |
| Analytics | throughput and review counts included the completed work |

## 2026-11-13 13:40 UTC — Start/stop script verification

`scripts/start.sh` and `scripts/stop.sh` were exercised on alternate ports with a throwaway `AATM_HOME`.

- **Defect found:** when the UI port was busy, Vite silently bound the next free port, so the script printed `http://127.0.0.1:5173` while the app was actually on `5174`. The advertised URL was wrong.
- **Fix 1:** `--strictPort`, so Vite fails instead of drifting.
- **Fix 2:** the script polls the UI for up to ~15 s and prints the URL only when it actually serves; otherwise it exits non-zero with the log path and an `AATM_UI_PORT=…` hint.
- **Verified:** a free port starts and serves (UI `5211` → 200, API `8127` → 200, exit 0); an occupied port now reports the busy-port error rather than a false URL.

## Not yet tested

- Windows 11 PowerShell path; no Windows host is available.
- PostgreSQL server integration.
- Visual browser-based Playwright E2E, full Arabic/Persian RTL verification, backup/restore, provider calls, agent execution, and Arena bridge interoperability.

This is a Phase 1 foundation verification report, not a final product verification report.

## RTL and locale verification (2026-11-13)

`npm run verify` runs `tsc --noEmit`, `vitest run`, `vite build` and the RTL CSS checker. Current result: TypeScript clean, **13 Vitest tests pass**, build succeeds, and the checker reports `0 physical` declarations in both `src/styles.css` (53,567 bytes, 26 logical inline declarations) and the built bundle.

Two real defects were found and fixed by writing these tests rather than assuming the UI was correct:

1. Arabic dates and numbers rendered with Latin digits (`13/11/2026`). The cause is that this ICU build's `ar` locale uses Latin digits while `fa` localizes. Fixed by formatting through `ar-u-nu-arab`; verified output is now `١٣‏/١١‏/٢٠٢٦`.
2. Three components formatted with the browser locale or an inline `Intl` call, independent of the chosen UI language.

The checker's detection power was proven with a probe file containing `margin-left`, an asymmetric `left`/`right` pair, and a lone `left`: all three were reported and the script exited 1.

## Reliability and performance (2026-11-13)

### Hardening tests (`tests/test_hardening.py`, 7 tests)

| Case | Expected | Result |
| --- | --- | --- |
| 1 MB + 10 byte POST | `413`, nothing written | pass |
| Valid form under the cap | `201` | pass |
| Understated `Content-Length` with a streaming body | `413` (bytes counted, header not trusted) | pass |
| Non-numeric `Content-Length` | `400` | pass |
| Headers on 200 and 404 responses | all six present | pass |
| Header duplication | none | pass |

### Measured latency (median of 7 runs, 120 tasks, 25 checkpoints, SQLite, this machine)

| Endpoint | Median |
| --- | --- |
| `GET /api/v1/tasks` (120 rows) | 5.6 ms |
| `GET /api/v1/dashboard` | 5.2 ms |
| `GET /api/v1/agents/center` | 17.1 ms |
| `GET /api/v1/tasks/{id}/timeline` | 6.0 ms |
| `GET /api/v1/projects/{id}/timeline` (before fix) | 94.1 ms |
| `GET /api/v1/projects/{id}/timeline` (after fix) | 12.1 ms |
| `POST /api/v1/blueprints` | 5.0 ms |

The project-timeline figure exposed a real N+1 query: the code called the per-task builder once per task, so query count grew with the number of tasks. It now issues one query per table for the whole project. The regression test asserts a generous ceiling, so it catches a return to quadratic behaviour without being flaky.

## UI render smoke test

`web/src/App.render.test.tsx` (jsdom) mounts the real `<App />` against mocked responses and clicks every navigation entry.

The value is entirely in the guards, and each one was added because the test lied without it:

- React reports render failures through `console.error` and unmounts the subtree rather than throwing, so an unguarded smoke test passes while a view is broken. The test fails on render-error messages.
- The first click loop included the already-active Dashboard, so "markup changed" was never true and the loop re-tested one view. The active entry is skipped and every other entry must change the markup.
- A deliberate `throw` was injected into a view to confirm the test fails; it does.

Frontend total: 16 tests.

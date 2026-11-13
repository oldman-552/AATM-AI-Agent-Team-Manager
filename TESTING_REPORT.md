# Testing Report

## 2026-11-13 — Environment inspection

- Scope: Repository and runtime availability.
- Result: Clean README-only starting branch; Python 3.11.2, Node.js 22.22.3, npm 10.9.2 available. Docker unavailable; Windows host unavailable.

## 2026-11-13 12:50 UTC — Backend tests (current)

- Latest command: `cd backend && ../.venv/bin/python -m pytest`.
- Result: **29 passed, 1 warning** (20 new tests).
- New coverage this slice:
  - `tests/test_provider_boundary.py` (10 tests): credential-reference validation and secret redaction; configurable pricing marked as estimate-only; budget consent/no-limit/limit-exceeded/idempotent-commit behaviour; monthly and per-scope limits; Arena hard block; Claude execution gating (disabled without explicit authorization, produces no call without consent, records usage once on replay, blocks when the global switch is off); credential redaction in provider errors; routing that never selects a paid provider without consent and never records usage; deterministic policies; and a socket-blocking test proving health/routing open no sockets.
  - `tests/test_provider_api.py` (6 tests): catalog contains no secret values; raw credentials and unknown fields are rejected; references are accepted and clearable; Arena cannot be enabled (409); budgets plus dry-run routing with zero usage records; settings validation and absence of any execute route; untrusted Host and hostile Origin rejection.
  - `tests/test_workflow.py` (4 tests): validated transitions with audit + idempotent replay; invalid/conflicting transitions rejected; evidence requirement; retry counting; dependency gating and ready queue; terminal states; transitions persisting across an application restart.
- Previously reported (historical, same tree minus this slice): 9 passed, 1 warning.
- Coverage: health/database query and default manager seed; project/agent/task creation and dashboard counts; invalid project/dependency and assignment clearing; role catalog count; 20-worker cap; file-backed database persistence across app restarts and idempotent migrations; untrusted Host rejection; progress event history/atomic status update, secret-pattern redaction, and idle-heartbeat behavior.
- Warning: Installed Starlette emits `StarletteDeprecationWarning` because its `TestClient` still uses `httpx`; test assertions passed. This is a dependency ecosystem warning, not suppressed.

## 2026-11-13 12:50 UTC — Frontend tests and build (current)

- `cd web && npm test` (Vitest 2.1.9) → **5 passed**.
  - Asserts English/Arabic/Persian are the only supported languages, that all three key sets are identical (216 keys each), that no translation is empty, that Arabic and Persian are genuinely distinct translations (not copies), and that `ar`/`fa` are RTL while `en` is LTR.
- `cd web && npm run build` (`tsc --noEmit && vite build`) → **Passed**; 1644 modules, `dist/assets/index-Cy8LTcBX.css` 26.65 kB, `dist/assets/index-BQ1zZENS.js` 318.84 kB.
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

## 2026-11-13 — Provider research

- Inspected upstream Arena Local Bridge v1.1.0 at commit `403122cf575b82aa519cad7c81a4cfe7d224d474` from its public repository.
- Result: Actual local OpenAI-compatible protocol and bearer-key/session behavior documented in `PROVIDER_RESEARCH.md`. No live bridge or Arena account was used because the inspected source includes CAPTCHA token generation/anti-automation behavior that conflicts with the explicit no-bypass requirement.

## Not yet tested

- Windows 11 PowerShell path; no Windows host is available.
- PostgreSQL server integration.
- Visual browser-based Playwright E2E, full Arabic/Persian RTL verification, backup/restore, provider calls, agent execution, and Arena bridge interoperability.

This is a Phase 1 foundation verification report, not a final product verification report.

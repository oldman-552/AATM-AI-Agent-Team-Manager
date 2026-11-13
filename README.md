# AATM — AI Agent Team Manager

A local-first command center for managing a team of AI agents: projects, tasks, a durable orchestrator, memory, planning, reviews, approvals, and honest reporting about what actually ran.

Everything runs on your machine against SQLite. There is no cloud dependency, no telemetry, and **no paid model call in the default build** — every capability that could spend money or touch the network is either off by default or refuses outright.

The complete product specification is preserved in [`AATM_MASTER_DEVELOPMENT_PROMPT.md`](AATM_MASTER_DEVELOPMENT_PROMPT.md).

## At a glance

| | |
|---|---|
| Backend | FastAPI + SQLAlchemy 2 + Alembic — **261 passed, 1 PostgreSQL-only test skipped locally** |
| Frontend | React 18 + TypeScript + Vite — **20 tests** |
| Languages | English, Arabic, Persian — **652 keys each**, parity enforced by test |
| Database | SQLite by default (WAL enabled); any SQLAlchemy URL via config |
| Migrations | 14 revisions; latest upgrade/downgrade round-trip verified |
| Layout | RTL verified by a CSS invariant checker (0 physical `left`/`right`) |

## Quick start

Requires Python 3.11+ and Node.js 20+.

```bash
scripts/install.sh
scripts/start.sh          # API on 127.0.0.1:8000, UI on 127.0.0.1:5173
scripts/stop.sh
```

Windows PowerShell equivalents (`install.ps1`, `start.ps1`, `stop.ps1`) are provided but **unverified** — no Windows host was available.

Verify it yourself:

```bash
(cd backend && ../.venv/bin/python -m pytest -o addopts="" -q)
(cd web && npm run verify)     # tsc + vitest + build + RTL checker
```

GitHub Actions runs the backend suite, a PostgreSQL migration/lock smoke test, and frontend verification on pushes and pull requests; see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## What actually works

**Records and workflow**
- Projects, agents, tasks with a validated state machine, dependency gating, replay-safe idempotency and append-only history.
- Agent lifecycle states and ten deny-by-default permission scopes, enforced server-side.
- Durable orchestrator: lease-based claims with heartbeat renewal during long executions, bounded parallel task execution (only when `max_concurrency > 1`), exponential backoff with a retry ceiling, and crash recovery for expired leases. Task/workflow DB changes are committed on the orchestrator thread; a database-wide expiring lock serializes API runs across processes, while a distributed worker pool remains open.
- Cooperative cancellation as a two-step protocol that never rewrites finished work.

**Execution (opt-in, local only)**
- `LocalProcessExecutor` runs one named, allow-listed command per task inside its isolated workspace.
- **A task names a command; it never contains one.** The argv lives in `.aatm/exec.json` that a human committed — executing a command string from the database would make every task title remote code execution.
- Off unless `AATM_EXECUTION_ENABLED=1`. No shell, bare allow-listed `argv[0]`, contained cwd, environment stripped to `PATH`/`LANG`, process-group kill on timeout, capped output.

**Memory and planning**
- Project-isolated memory with scopes, keyword retrieval, version history, rollback and export.
- Budgeted memory context selection with an explicit exclusion list, plus extractive summaries labelled as such.
- Deterministic Manager planning producing reviewable proposals that are re-validated on apply.

**Reporting**
- Analytics computed only from stored rows, with sample sizes stated and no synthetic scores.
- AI Team Intelligence Center: complexity-weighted agent metrics where thin samples are flagged, empty metrics are `null` never `0`, and rule-based assessments are kept in separate fields from measurements. No ranking by task count.
- Live audit stream over SSE with a resumable cursor and its transport labelled honestly as *polled*.
- Self-healing surface: classified database errors, queue health, and a capability table where only the two genuinely automatic recoveries are marked automatic.
- Local CPU/memory/disk-based adaptive cap: off by default; when `AATM_ADAPTIVE_CONCURRENCY=1`, it can only reduce the per-run dispatch batch below `AATM_MAX_CONCURRENCY`, subtracts already-running tasks, and reports the applied cap. A cap above one runs tasks from different projects concurrently in a bounded thread pool; tasks in the same project share a workspace and are not batched together. DB changes stay on the orchestrator thread. Run requests sharing one database are serialized across API processes by an expiring database lock; this is not a distributed worker pool or task semaphore.

**Safety and operations**
- Approval-gated pull-request plans showing exact commands, never calling the network.
- Isolated browser profile directories with exclusive locks (no browser is launched).
- Optional bearer-token auth with the token injected by the dev proxy, never shipped to the browser; CSRF-hardened mutations.
- Verified SQLite backup/restore, request-body caps, security headers, and a progress system that never claims work occurred just because a timestamp changed.

## What is deliberately not built

Roughly 20% of the specification is open, and none of it is silently skipped:

| Category | Item |
|---|---|
| Gated by design | Live paid provider calls — the consent/accounting surface does not exist, and nothing spends money without it |
| Gated by design | Model-driven task execution — the executor runs local commands, never a model |
| Gated by design | GitHub push/PR execution — plans are recorded and approval-gated; nothing executes |
| Blocked on policy | Arena integration — the upstream bridge generates CAPTCHA tokens and hides automation signals, contradicting the no-bypass requirement. See [`BLOCKERS.txt`](BLOCKERS.txt) |
| Environment-limited | Windows 11, PostgreSQL, Docker, Playwright — unavailable on the development host; recorded as limits, never simulated |

Creating or moving a task record does not execute it unless execution is explicitly enabled. The Manager record makes no AI calls. **No paid request has ever been made.**

## API surface

Health, dashboard, projects, agents, tasks, workflow, orchestrator, memory, planning, quality/reviews, approvals, workspaces, checkpoints, browser profiles, providers (offline), analytics, intelligence, recovery, notifications, settings, events, and a live SSE stream.

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/orchestrator/status
curl -N "http://127.0.0.1:8000/api/v1/events/stream?max_seconds=10"
```

Interactive docs at `http://127.0.0.1:8000/docs`. Full route reference and request examples: [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md).

## Project layout

```
backend/
  app/            FastAPI routers, domain modules, execution, events
  tests/          32 test modules, 262 cases
  migrations/     14 Alembic revisions
web/
  src/            React views, typed API client, i18n resources
scripts/          install/start/stop/update/uninstall (sh + ps1), backup, progress reporter
```

## Documentation

| Document | Contents |
|---|---|
| [`STATUS.txt`](STATUS.txt) | Live status, current phase, verified test counts |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Modules and the guarantees each one holds |
| [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) | Every endpoint, including the executor's safety rules |
| [`TESTING_REPORT.md`](TESTING_REPORT.md) | Test strategy and what each guard protects |
| [`SECURITY.md`](SECURITY.md) | Threat model and security boundaries |
| [`BLOCKERS.txt`](BLOCKERS.txt) | Blocked and environment-limited items |
| [`NEXT_ACTIONS.txt`](NEXT_ACTIONS.txt) | Prioritised remaining work |
| [`PROGRESS_LOG.txt`](PROGRESS_LOG.txt) | Chronological development log |
| [`INSTALLATION.md`](INSTALLATION.md) · [`CONFIGURATION.md`](CONFIGURATION.md) | Setup and configuration |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed and why |

To record progress atomically:

```bash
.venv/bin/python scripts/progress_reporter.py event \
  --phase 'Phase 29 — ...' --task '...' --action '...' \
  --activity '...' --tests 'Not run' --results 'Event recorded; no verification claimed'
```

## Status and security

**The application is not production-ready.** Do not expose the API to an untrusted network. There is no multi-user authentication or per-user authorization. Never commit secrets, credentials, or browser profiles — the repository contains none, and a tracked-file secret scan is clean.

Provider keys, when they eventually exist, are read only from environment variables or the OS keyring; no HTTP endpoint accepts a raw key.

## License

See the repository for licensing terms.

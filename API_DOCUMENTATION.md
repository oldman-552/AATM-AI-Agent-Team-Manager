# AATM API Documentation

## Status and security

This API implements the Phase 1 data foundation plus an **offline** provider boundary and a task workflow state machine. No endpoint performs a live AI provider request, and no endpoint executes a task. It is intended for loopback use and has no multi-user authentication; do not expose it to an untrusted network. The Vite UI sends relative `/api/v1` requests through its development proxy.

OpenAPI schema and interactive docs are available at `/openapi.json` and `/docs` when the backend is running.

## Authentication

Default mode is `off`: requests from local tooling work without credentials, but any mutating request carrying a foreign `Origin` is rejected with 403 (CSRF hardening).

With `AATM_AUTH_MODE=token`, every `/api/v1` request except `GET /api/v1/health` requires `Authorization: Bearer <AATM_AUTH_TOKEN>`; missing or wrong tokens return 401 with `WWW-Authenticate: Bearer`. Tokens are compared in constant time and never appear in responses. The Vite dev proxy injects the header server-side when `AATM_AUTH_TOKEN` is present in its environment, so the browser bundle carries no secret.

## Conventions

- Base path: `/api/v1`.
- JSON request/response bodies.
- Timestamps are stored in UTC; SQLite may serialize them without a trailing timezone marker, so clients should treat naive timestamps as UTC.
- List endpoints accept `limit` from 1 to 500 (default 100).
- Validation failures use FastAPI/Pydantic's standard 422 response; missing related project/agent/task records use 404; the 20-worker registration limit uses 409.

## Endpoints

### `GET /health`

Performs an actual `SELECT 1` against the configured database.

Example response:

```json
{"status":"ok","application":"AATM — AI Agent Team Manager","version":"0.1.0","database":"ok"}
```

### `GET /dashboard`

Returns persisted project, agent, task, status/state counts, and up to eight recent audit events. A default Manager identity is inserted once at startup with provider `unconfigured`; it is a database record, not an active AI process.

### Projects

- `GET /projects?limit=100`
- `POST /projects` — `{ "name": "Website", "description": "Optional description" }`

Names are required and trimmed. New projects generate an audit event.

### Agent role templates and registrations

- `GET /agent-roles` — 20 built-in worker role templates.
- `GET /agents?limit=100`
- `POST /agents` — `{ "name": "QA One", "role": "QA Engineer", "description": "Optional" }`

Registrations are metadata only. Provider defaults to `unconfigured`; no credentials or execution are available. At most 20 worker records can be registered; the Manager record does not count toward that limit.

### Tasks

- `GET /tasks?limit=100`
- `POST /tasks` — accepts `title`, optional `description`, `project_id`, `assigned_agent_id`, `priority`, `dependencies`, and `acceptance_criteria`.
- `PATCH /tasks/{task_id}/assignment` — `{ "assigned_agent_id": "<agent-id>" }` or `null` to clear assignment.

A created unassigned task starts `pending`; one created with an agent starts `assigned`. Dependency IDs must refer to existing tasks.

Priorities are `low`, `normal`, `high`, or `urgent`. State changes go through the validated workflow endpoints below; no task execution endpoint exists in this build.

### Audit events

- `GET /events?limit=100`

The initial audit trail records manager initialization, project/agent/task creation, and assignment changes. This is not yet a complete security audit system.


## Task workflow

State is owned by the server (`backend/app/workflow.py`). A client cannot invent a transition.

### `GET /tasks/workflow`

Returns the transition map, dependency-satisfied states, and evidence-required states. No execution occurs.

### `GET /tasks/ready?limit=100`

Returns assigned tasks whose dependencies are all in `completed`/`approved`, ordered by priority then creation time. This is a **state-based ready queue**, not a running scheduler; the response includes a note stating nothing is executed.

### `PATCH /tasks/{task_id}/state`

```json
{ "target_state": "running", "idempotency_key": "agent-7-run-1", "note": "optional evidence", "output": null, "error": null }
```

- Transitions are validated against a fixed map; an invalid transition returns 409 with the allowed targets.
- `running` requires an assigned agent and satisfied dependencies (409 otherwise).
- `failed`, `approved`, and `rework_required` require a non-empty note as evidence.
- `failed`/`rework_required` increment `retry_count`.
- Replaying the same `idempotency_key` for the same target returns `transition_created: false` and writes no duplicate history/audit event; reusing the key for a different target returns 409.
- Response: `{ "task": {...}, "transition_created": true, "allowed_next_states": ["waiting","completed","failed","cancelled"] }`.

### `GET /tasks/{task_id}/transitions`

Append-only history (`from_state`, `to_state`, `idempotency_key`, `note`, `created_at`).

## Providers (offline only)

Non-negotiable behaviour: every provider endpoint below is **offline**. There is no endpoint that performs a live model request, and no endpoint accepts, stores, logs, or returns a credential value.

### `GET /providers`

Returns provider descriptors (name, paid/free, compliance note, safe configuration, offline health), routing settings, budget limits, the pricing estimate basis, and `live_requests_allowed: false`.

### `GET /providers/{provider_id}` and `GET /providers/{provider_id}/health`

Offline health only. Possible states: `offline_ready`, `unconfigured`, `disabled`, `blocked`, `budget_exhausted`, `not_permitted`. `live_calls_enabled` is always `false`. `arena_bridge` always reports `blocked` with the CAPTCHA/bridge reasons.

### `PATCH /providers/{provider_id}/config`

```json
{ "enabled": true, "model": "<verified-model-id>", "credential_ref": "env:ANTHROPIC_API_KEY" }
```

- Only credential **references** are accepted: `env:NAME` or `keyring:service/account`. Raw keys, `file:`/URL schemes, and unknown fields (for example `api_key`) are rejected with 422.
- `clear_credential: true` removes the reference; combining it with `credential_ref` is a 422.
- `base_url` is restricted to the official Anthropic host or a loopback proxy.
- Any attempt to enable or configure `arena_bridge` returns 409.
- Values are persisted in `provider_configs.credential_ref`; the secret itself is resolved in-process only during an authorized execution attempt that no HTTP route exposes.

### `GET|PATCH /providers/settings`

Routing policy (`arena_first`, `claude_first`, `manual`, `task_based`, `user_defined`), default model label, and user-defined order. Unknown policies or providers are rejected. `live_requests_allowed` is hard-coded `false` and cannot be set over HTTP.

### `POST /providers/route`

Dry-run routing decision. Body: `policy`, `preferred_provider`, `provider_order`, `complexity`, `agent_id`, `project_id`, `model`, `estimated_input_tokens`, `estimated_output_tokens`, `max_tokens`, `paid_consent`.

Returns `status` (`selected` | `no_eligible_provider`), the selected provider/model, per-candidate reasons, the cost **estimate**, the budget check, and `execution_performed: false`. A paid provider is never selected without `paid_consent: true` **and** a positive applicable budget limit. Routing never writes a usage record and never spends money. Unknown agent/project IDs return 404.

### `GET /budgets` and `PUT /budgets`

`PUT` upserts one limit: `{ "scope": "daily", "provider_id": "anthropic", "limit_usd": 0.5, "scope_key": null }`. Scopes: `daily`, `monthly`, `agent`, `project`, `credential`, `global`. `provider_id` accepts a known provider or `*`.

Enforcement rules (server-side, not advisory):
- Paid usage is denied without explicit per-request consent.
- Paid usage is denied when no positive limit applies.
- Every applicable limit must have room for the estimate.
- Records are keyed by an idempotency key, so a replay cannot double count.
- Per-agent/per-project/per-key scopes fail closed when the corresponding scope value is missing.

### `GET /usage`

Aggregated usage plus the most recent records. Costs carry `billing_status: "estimated"`; confirmed billing is only present if a reconciliation process imported it (`confirmed_cost_usd`), which does not exist yet. No provider billing API is called.

## Orchestrator (inspection and recovery only)

The durable orchestrator (`backend/app/orchestrator.py`) dispatches work through an injectable `TaskExecutor`. The HTTP surface deliberately **cannot** start a run: the configured executor is `DisabledExecutor`, which refuses to execute and never simulates work.

### `GET /orchestrator/status`

Returns the configured executor (and its refusal reason), counts (`running`, `waiting_for_retry`, `expired_leases`, `assigned`, `failed`), active leases with owner/expiry, and the retry queue.

### `POST /orchestrator/recover`

Returns tasks whose lease expired to `assigned`, records the interrupted attempt as a failure (so retry counting and claim keys stay distinct), releases the lease, and writes a `task.lease_recovered` audit event. Idempotent: a second call returns `count: 0`.

Concurrency and retry semantics (server-side):
- `max_concurrency` bounds how many tasks a single run may claim.
- A claim requires `assigned` state, an agent, satisfied dependencies (`completed`/`approved`), and an elapsed backoff window.
- Claims write a lease; an active lease is never stolen, and an expired lease is always recoverable.
- Executor exceptions are recorded as `Executor error: <Type>` only — executor messages are never propagated, so they cannot leak secrets into task records.
- A completion requires non-empty evidence; otherwise the task fails and is retried.

## Independent QA reviews

Reviewer separation and evidence are enforced by the server (`backend/app/quality.py`).

### `GET /tasks/{task_id}/reviews`

Review history for one task. `GET /reviews?limit=100` lists recent reviews across tasks.

### `POST /tasks/{task_id}/reviews` → 201

```json
{
  "reviewer_agent_id": "<agent-id>",
  "verdict": "approved",
  "summary": "Independently verified.",
  "checks": [{"check": "unit tests", "result": "51 passed"}],
  "idempotency_key": "review-1"
}
```

- The reviewer must be a registered agent and **must differ** from the task's assignee (409 otherwise).
- `approved` requires at least one concrete non-empty check **and** recorded task output; `rework_required` requires a summary.
- The verdict drives the existing state machine: `completed → reviewing → approved | rework_required`, so no new state path is invented.
- Replaying an idempotency key returns `created: false`; reusing it for a different verdict is a 409.
- Audit events: `task.review_approved` / `task.review_rework_required`.

## Approval gates

### `GET /approvals?status=pending|approved|rejected`

### `POST /approvals` → 201

```json
{ "kind": "deployment", "entity_type": "task", "entity_id": null, "summary": "Deploy staging build" }
```

Kinds: `paid_provider_request`, `protected_branch_merge`, `deployment`, `data_deletion`. A referenced task must exist (404 otherwise).

### `PATCH /approvals/{approval_id}`

```json
{ "status": "approved", "decided_by": "local-user", "note": "Reviewed the diff." }
```

Records a human decision only. Deciding an already-decided request returns 409. The response states explicitly that the gated action is **not** executed by this build — no endpoint performs deployments, merges, deletions, or paid provider traffic.

## Project workspaces (isolated Git)

Workspaces live under `AATM_WORKSPACES_ROOT` (default `$AATM_HOME/workspaces`), never inside the AATM repository.

### `GET /projects/{project_id}/workspace`

Returns the stored workspace plus a read-only Git status (`branch`, `head_commit`, `on_protected_branch`, `clean`, `changed_files`, `changed_count`, `diffstat`). Returns `workspace: null` when none exists.

### `POST /projects/{project_id}/workspace` → 201

```json
{ "local_source": "/absolute/path/to/local/repo", "branch": "aatm/task-1" }
```

- `local_source` must be an existing **local** Git repository; network URLs are rejected by contract (only a filesystem path is accepted).
- With no source, a fresh local repository with an initial commit is created.
- `branch` must pass validation and must not be `main`/`master`.
- One workspace per project (409 on duplicates).

### `POST /projects/{project_id}/workspace/branches` → 201

Creates and checks out a new work branch. Protected branch names are rejected with 422.

### `DELETE /projects/{project_id}/workspace`

Removes only the AATM-created workspace directory after re-validating that it is inside the configured root; the record and an audit event are updated. It does not run destructive Git commands and never touches the source repository.

Not implemented (and deliberately not reachable): merge, push, fetch from remotes, force operations, and branch deletion. No Git command runs with credentials, and `GIT_TERMINAL_PROMPT=0` plus a scrubbed environment prevent interactive prompts.

## Project memory (isolated, versioned)

Scopes: `global`, `project`, `agent`, `task`, `decision`. Any non-global entry is bound to a project and is **only** visible/editable within that project; `global` entries are shared. Retrieval is deterministic local keyword overlap — no embeddings and no network call.

- `GET /memory?project_id=&scope=&include_global=true` — visible entries. Omitting `project_id` returns global entries only.
- `POST /memory` → 201 — `{title, content, scope, key?, project_id?, agent_id?, task_id?, tags?}`. Providing an existing `key` inside the same project creates a **new version** instead of a duplicate (`created: false`).
- `GET /memory/search?q=&project_id=&limit=` — scored results restricted to visible memory. A blank query is rejected.
- `GET /memory/{entry_id}?project_id=` — entry plus full version history; 404 when the entry belongs to another project.
- `POST /memory/{entry_id}/rollback/{version}` — restores content from an earlier version **as a new version** (history is never rewritten).
- `DELETE /memory/{entry_id}?project_id=` — explicit deletion, including its history, with an audit event.
- `GET /memory/export?project_id=` — JSON export of visible memory.

Validation: project-bound scopes require `project_id`; `agent` requires `agent_id`; `task` requires `task_id`; titles/content are bounded (200 / 20,000 chars).

## Agent lifecycle and permissions (`/agents`)

**Lifecycle** `idle → active → paused → active`; any state → `disabled` (and `disabled` is terminal until re-enabled out of band). Illegal jumps are 409, the Manager identity cannot be disabled, and an agent that is paused, disabled, offline or the Manager cannot receive work — that is enforced on both `POST /tasks` and `PATCH /tasks/{id}/assignment`, not just in the UI. Work already held is **not** silently dropped; `GET /agents/blocked` reports agents holding open work while unavailable.

- `GET /agents/scopes` — the scope list and the `deny` default.
- `PATCH /agents/{id}/state` — `{target_state, note}` (409 on an illegal transition, 404 unknown agent).
- `PATCH /agents/{id}/permissions` — replaces the scope list; unknown scopes are 422, duplicates are collapsed, and changes are audited.
- `GET /agents/blocked` — agents with open work but a non-working state.

Scopes: `task:read`, `task:write`, `task:assign` (Manager-only, enforced by `require_scope`), `review:submit`, `memory:write`, `workspace:write`. Agents are created with no scopes unless explicitly granted.

## Manager planning (`/planning`)

Deterministic rules over persisted rows — **no model is called**, and nothing is written by `proposals`.

- `GET /planning/proposals?project_id=` — `findings` (running-without-agent, blocked-but-assigned, awaiting review, dependency cycles), `proposals` (task → least-loaded active agent, with `reason_code`/`reason_data`), a dependency-respecting `order`, `dependency_cycles`, an idempotent `plan_id`, and `applies_automatically: false`.
- `POST /planning/apply` — `{plan, actor}`. Re-validates every proposal against current state and skips stale ones with a reason (`missing_task`, `state_changed`, `already_assigned`, `agent_unavailable`). Applied assignments and the application itself are audited. A plan without `plan_id` is rejected (422), and a plan for an unknown project is a 404.

Agents are a shared worker pool today (agents are not project-scoped), so planning balances across all non-manager, non-offline agents.

## Preferences (`/settings`)

Non-secret, allow-listed preferences persisted in `app_settings` under `user_preferences`:
`language` (`en|ar|fa`), `theme` (`dark|light`), `page_size` (`10|20|50|100`), `notification_poll_seconds` (10–600), `checkpoint_retention` (1–500), `backup_retention` (1–100).

- `GET /settings` — current values merged over defaults, plus `defaults` and a boundary note.
- `PATCH /settings` — partial update; unknown fields are rejected (`extra="forbid"`), so `api_key`, `token` or `password` can never be stored. Changes are audited without values.
- `POST /settings/reset` — restore defaults (audited).
- `GET /settings/export` — non-secret settings for a backup.

## Notifications (derived, with persisted read state)

- `GET /notifications` — `{notifications, unread, total, source}`. Each item has `kind`, `message_key` + `data` (for client-side translation), `action_view`, `severity`, `read` and `read_at`.
- `POST /notifications/read` — `{ids: ["<kind>:<uuid>", ...]}` persists read state (422 for malformed ids).
- `POST /notifications/read-all` — marks every currently unread derived notification read (idempotent).
- `DELETE /notifications/read-state?older_than_days=90` — retention for the read-state table.

Notifications are **derived**, never fabricated: pending approvals, tasks in `failed`/`rework_required`, and tasks with an expired lease. Deciding an approval removes its notification because the underlying row no longer needs attention. Messages are returned as translation keys plus data, so the server never hardcodes a language.

## Analytics (derived from stored rows)

Read-only, no synthetic scores. `days` is bounded to 1–90 (422 otherwise).

- `GET /analytics?days=14` — counts, throughput, activity, cycle time, review outcomes, rework and approval totals, plus explicit `notes`.
- `GET /analytics/throughput`, `/cycle-time`, `/reviews`, `/rework`, `/approvals`, `/activity` — the same sections individually.

Honesty rules baked into the response:
- A metric with no data returns `null` (for example `cycle_time.average_seconds`), never `0` that could read as "instantaneous".
- Cycle time reports `samples`; tasks without a terminal transition are excluded and counted separately.
- Provider cost analytics are **absent** because live provider traffic does not exist; the endpoint says so in `notes`.

## Pull-request plans (no network)

Planning and gating only. No token is read, no HTTP request to GitHub is made, and nothing is pushed.

- `GET /projects/{project_id}/pull-requests` — plans with status, `executed: false`, `execution_available: false`, and the inert command list a future executor would run.
- `POST /projects/{project_id}/pull-requests` → 201 — `{owner, repo, base_branch, head_branch, title, body}`. Creates the plan plus a linked `pull_request` approval request. Duplicate open plans for the same repo + head branch are rejected (422).
- `POST /projects/{project_id}/pull-requests/{plan_id}/decision` — `{status: approved|rejected, decided_by}` drives the linked approval; the plan moves to `approved_not_executed` or `rejected`. A repeat decision returns 409.
- `POST /projects/{project_id}/pull-requests/{plan_id}/execute` — **always 409** with `executed: false` and a reason. This is intentional: an endpoint that pretends to open a PR would be a fabricated success.

Validation: owner (`^[A-Za-z0-9][A-Za-z0-9-]{0,38}$`, no trailing dash), repository charset, safe base/head branch names, head ≠ base, title 1–200 characters, body ≤ 20,000.

## Task checkpoints and resume plans

- `POST /tasks/{task_id}/checkpoints` → 201 — `{label, state, note}`. Sequences are monotonic per task and history is append-only. Values that look like credentials (a key named like a token/password, or a value matching a known key shape) are rejected with 422 so secrets never reach the database or its backups.
- `GET /tasks/{task_id}/checkpoints` — ordered checkpoints.
- `GET /tasks/{task_id}/resume-plan` — `next_actions` guidance plus `latest_checkpoint`, `lease_expires_at` and `checkpoint_count`. `resumed_automatically` is always `false`: AATM never claims work resumed on its own.
- `DELETE /tasks/{task_id}/checkpoints?keep=20` — retention trimming for one task.

`CORS` now allows `DELETE` so a browser-originated retention call is not blocked by preflight.

## Backup and restore (CLI)

Backup is a local operator command, not an HTTP endpoint — destructive operations are deliberately not exposed over the API.

- `scripts/backup.py create --name <name>` — consistent online SQLite backup plus a manifest with SHA-256.
- `scripts/backup.py list` / `verify --name <name>` — hash + `PRAGMA integrity_check` verification.
- `scripts/backup.py restore --name <name> --allow-overwrite --yes` — verified restore with a preserved previous copy.
- `scripts/backup.py prune --keep N` — retention cleanup.

## System resources

### `GET /system/resources?configured_max=2`

Returns a **local** snapshot (CPU percent from load average, memory from `/proc/meminfo` or `os.sysconf`, disk from the database directory) and a bounded concurrency recommendation. `applied_automatically` is always `false`: the orchestrator's configured `max_concurrency` remains authoritative, and the recommendation is advisory only. Nothing is uploaded.

Recommendation rules: bounded by `1..min(configured_max, 4, cpu_count)`; memory pressure at ≥90% or disk pressure at ≥95% forces the floor; load per core ≥1.0 halves the result.

## Audit events added in this slice

`task.state_changed`, `task.lease_recovered`, `task.review_approved`, `task.review_rework_required`, `approval.requested`, `approval.approved`, `approval.rejected`, `project.workspace_created`, `project.workspace_branch_created`, `project.workspace_removed`, `memory.created`, `memory.versioned`, `memory.rolled_back`, `memory.deleted`, `task.checkpointed`, `github.plan_created`, `github.plan_approved`, `provider.config_updated`, `providers.settings_updated`, and `budget.limit_updated` join the existing creation/assignment events. Audit summaries deliberately exclude credential values.

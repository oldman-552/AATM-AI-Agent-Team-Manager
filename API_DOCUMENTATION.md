# AATM API Documentation

## Status and security

This API implements the Phase 1 data foundation plus an **offline** provider boundary and a task workflow state machine. No endpoint performs a live AI provider request, and no endpoint executes a task. It is intended for loopback use and has no multi-user authentication; do not expose it to an untrusted network. The Vite UI sends relative `/api/v1` requests through its development proxy.

OpenAPI schema and interactive docs are available at `/openapi.json` and `/docs` when the backend is running.

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

## Audit events added in this slice

`task.state_changed`, `task.lease_recovered`, `task.review_approved`, `task.review_rework_required`, `approval.requested`, `approval.approved`, `approval.rejected`, `project.workspace_created`, `project.workspace_branch_created`, `project.workspace_removed`, `provider.config_updated`, `providers.settings_updated`, and `budget.limit_updated` join the existing creation/assignment events. Audit summaries deliberately exclude credential values.

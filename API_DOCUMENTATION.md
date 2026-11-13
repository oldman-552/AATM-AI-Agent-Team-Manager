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

## Browser profiles (`/browser-profiles`)

Registry + isolated on-disk directories. **No browser is launched or driven**, no cookie/login/session material is read, and `session_state` is always `not_inspected`.

- `GET /browser-profiles?agent_id=` — profiles with `exists`, `size_bytes`, `entries`, `modified_at`, `status`, lock owner, plus `automation_available: false` and an explicit reason.
- `POST /browser-profiles` → 201 — `{name, label?, agent_id?, isolation}`. Creates a real directory under `AATM_BROWSER_PROFILES_ROOT`; names are validated (no `..`, no separators) and unique.
- `PATCH /browser-profiles/{id}` — label/owner change; `{clear_agent: true}` detaches.
- `PATCH /browser-profiles/{id}/state` — `created|ready|locked|archived` with validated transitions; `archived` is terminal.
- `POST /browser-profiles/{id}/lock` — exclusive; a second lock is 409 and names the current holder. `POST .../unlock` releases.
- `DELETE /browser-profiles/{id}?confirm=true` — removes the directory and the record; refused with 422 without `confirm` and 409 while locked. Reports `removed_bytes`.

Directories are reported relative to the root (`name/`), not as absolute host paths.

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

## Execution timeline and cancellation

The timeline is a **projection of stored rows**, never a reconstruction. Each entry names the table it came from (`source`), so any claim on screen can be audited in the database.

### `GET /tasks/{task_id}/timeline?limit=200`

Merges `task_transitions`, `task_checkpoints`, task-scoped `audit_events`, `review_records` and `approval_requests`, sorted by `(at, kind, reference)` with a stable tiebreaker. Returns `entries[]` (`at`, `kind`, `title_key`, `data`, `detail`, `reference`, `source`), plus `total`, `truncated`, `sources` and a `note` restating that assembly is read-only.

### `GET /projects/{project_id}/timeline?limit=100`

Newest-first across the project's tasks; each entry also carries `task_id` and `task_title`. `404` for an unknown project.

### Cancellation is a two-step protocol

1. `POST /tasks/{task_id}/cancel` with `{"reason": "..."}` records **intent** (`cancel_requested_at`, `cancel_reason`) and an audit event. It deliberately does **not** change `state`: an executor may still be mid-flight. `409` when already requested, already cancelled, or when the task already reached `completed`/`approved` — finished work is never rewritten.
2. `POST /tasks/{task_id}/cancel/apply` honours the request at a safe boundary. Returns `{"cancelled": true|false, "reason"}` where `reason` may be `no_pending_request`, `already_finished` or `not_cancellable`.

`DELETE /tasks/{task_id}/cancel` withdraws a pending request. `GET /cancellations` lists pending requests; `POST /cancellations/apply` applies them all (operator action, also used by the orchestrator).

`Orchestrator.run_once` honours pending cancellations **before** claiming anything, and reports them in `cancelled[]`; a cancelled task is therefore never started. The workflow itself requires a reason note for any `cancelled` transition (a `409` without one), and `reviewing → cancelled` is now a legal transition.

Audit events added: `task.cancel_requested`, `task.cancel_withdrawn`, `task.cancelled`.

## Live Agent Control Center

Every field is read from a stored row at request time, or is `null`. There is no simulated progress anywhere.

- `GET /agents/center` — all agents with their live state; `GET /agents/{id}/center` — one agent.
- Payload per agent: `status`, `current_task` (newest open task or `null`), `open_tasks`, `latest_activity` (newest `audit_events` row about the agent or its tasks), `execution_time` (wall clock, explicitly labelled `wall_clock_not_cpu`), `usage` (estimated vs confirmed cost, `cost_source`: `none` | `estimate_only` | `mixed`), `leases`, `browser` (`automation_available: false`), `authentication` (never a credential), `errors`, `history`, plus `controls` describing what the backend can actually do and an `honesty` block restating the provenance.
- `POST /agents/{id}/instructions` — records an operator instruction (optionally tied to one of that agent's tasks, `409` otherwise). `delivered` is `false` until a real executor reports consuming it; none is configured.
- `GET /agents/{id}/instructions` — recorded instructions with `delivery_note`.
- `POST /agents/{id}/reassign` — moves a task to another worker or back to the queue. Refuses the Manager, paused/disabled/offline targets, tasks not held by that agent, finished work, and a leased running task. Audited as `task.reassigned`.

The Control Center view in the UI renders these values with the same rules: missing data shows as "no recorded data", estimated cost is labelled unconfirmed, and "open browser" is shown as unavailable rather than as a dead button.

Audit events added: `agent.instruction_issued`, `task.reassigned`.

## AI Project Builder

- `POST /blueprints` — body: `idea` (20–4000 chars), `scale` (`prototype|mvp|production`), `stack` (`python-react|node-react|python-only`), `data_layer` (`sqlite|postgres`), `team_size` (1–20). Returns all eleven plan sections: requirements, architecture, technology stack, database design, development phases, task breakdown, assignment plan, dependencies, testing strategy, acceptance criteria and delivery plan.
- Generation is **deterministic rules, not a model**: `generation.model_called` is `false`, and `detection_evidence` lists the keywords that selected each capability pack, so a reader can see exactly why a requirement exists.
- Proposing writes nothing. Every request is a fresh proposal with a `fingerprint`.
- `POST /blueprints/apply` — body: `plan`, `confirmed`. Without `confirmed: true` it returns `409` and creates nothing. It re-validates task keys, duplicate keys and dependency references (`422`), then creates the project plus dependency-linked tasks in `pending`/`assigned`. Nothing is executed: the orchestrator remains the only path to running work. Audit events: `project.created`, `blueprint.applied`.

Assignments only ever name registered workers whose role matches; unmatched tasks say so in `reason` rather than being silently assigned.

## Permission levels

`GET /agents/scopes` returns the nine levels the specification names, each mapped to a scope, plus `enforced_at` describing the single boundary where each is checked and `approval_only` listing the three scopes that can only record an approval.

| Level | Scope | Enforced at |
| --- | --- | --- |
| Read Only | `task:read` | reading a task timeline |
| Development | `task:write` | an agent taking assigned work; advancing task state on its behalf |
| Testing | `review:submit` | recording a review verdict |
| File Modification | `memory:write` | writing project memory |
| Git Commit | `workspace:write` | creating a branch or file in a project workspace |
| Pull Request | `pull_request:plan` | recording a pull-request plan |
| Branch Merge | `merge:approve` | approving a protected merge (recording only) |
| External API Operations | `external:approve` | approving a paid/external call (recording only) |
| Production Access | `production:approve` | approving a deployment (recording only) |

Permissions remain deny-by-default. The three approval-only scopes are Manager-reserved and are refused for workers *before* the grant is consulted, so a bad row cannot silently confer merge rights. No scope authorises executing a gated action in this build.

A Manager plan (`POST /planning/apply`) now skips any agent that has not declared `task:write`, recording `agent_lacks_task_write_scope` instead of quietly assigning work to an agent with no declared permission.

## Self-healing and recovery

- `GET /recovery` — one honest page: a real database probe with timing and a SQLite integrity check, queue health (recoverable vs exhausted tasks, retry ceiling), and a capability table. Each capability states whether it is detected, whether AATM acts **automatically**, and what it actually does.
- `GET /recovery/database` — a real `SELECT 1` with elapsed time and, on failure, a classified cause.
- Only two recoveries are marked `automatic: true`: expired-lease reclaim by the orchestrator, and restart survival through durable SQLite state. Browser and provider failures are reported as `handled: false` with the reason they cannot occur here, rather than claimed as covered.

### Database errors

Unhandled `SQLAlchemyError` becomes a classified JSON body instead of an opaque 500: `locked`/`constraint` → `409`, `schema`/`corrupt`/`unavailable` → `503`, each with `advice` and an explicit `automatic_recovery: false`. `GET /health` returns `200` when the probe succeeds and `503` with `status: "degraded"` when it fails.

Sessions now roll back before closing, so a failed transaction cannot poison the next request that reuses a pooled connection. Retries are restricted to genuine lock contention: an integrity error would fail identically on retry, so retrying it would only hide the defect.

## Memory context selection and summarization

- `GET /memory/context?project_id=&q=&word_budget=60&scope=&agent_id=&task_id=` — selects the memory that fits a **word** budget. Deterministic ranking: relevance (keyword overlap), then scope priority (`decision` 100, `project` 70, `global` 60, `agent` 40, `task` 30), then recency, then title.
- Returns `selected[]` (`included_as`: `full` | `summary`, plus `words` and `relevance`), `excluded[]` with the reason each entry was omitted, and `stats` where `selected + excluded == candidates`.
- The budget reports `unit: "words"` and says plainly that these are **not provider tokens**: AATM has no tokenizer for an arbitrary model, and a fake token count would be worse than an honest approximation.
- `GET /memory/summarize/{entry_id}?max_words=&q=` — an **extractive** summary. Sentences are copied verbatim and `method` is `extractive` (or `title_only` when the entry has no body). AATM has no model to paraphrase with, so it never invents one.

When an entry would exceed the remaining budget, it is reduced to a verbatim extract before being dropped: losing a relevant decision entirely is more expensive than including it in part.

## AI Team Intelligence Center

`GET /intelligence?days=90` — measured agent performance plus rule-based assessments, in **separate fields**.

### Measured (counted from rows)

Per agent: `tasks` (total/terminal/open/success/failed/cancelled), `success_rate`, `complexity_points`, `complexity_points_per_task`, `by_complexity`, `rework`, `reviews` (received, not given), `completion_time` (median/fastest/slowest) and `usage`.

Two fairness rules are enforced in the data, not by convention:

- **Complexity is weighted** (`low` 1, `normal` 2, `high` 4, `urgent` 6), so four small tasks do not outrank one urgent task by default.
- **`success_rate` counts successes and failures in the denominator** and excludes cancellations: a withdrawal outside the agent's control is not evidence about the agent, and counting it as a failure would be unfair. The rule is published in `success_rate_denominator`.
- `sample_sufficient` is `false` below `min_sample` (3) terminal tasks; an empty metric is `null`, never `0`.

### Assessed (rule-based, labelled)

`assessments[]` entries carry `kind: "rule_based"`, the `basis` metric and threshold, a `recommendation` and a `caveat`. `method.model_generated` is `false` and `method.ranking` is `"none"`: agents are **not** ranked by task count, and no overall ordering is produced.

## Live event stream (server-sent events)

`GET /events/stream?last_event_id&poll_seconds&heartbeat_seconds&max_seconds` — `text/event-stream`.

The specification asks for real-time updates *where appropriate*. This build is local and SQLite-backed with no message broker, so the stream **polls the audit table** and says so in its `hello` frame (`delivery: "poll"`, plus a note stating events are not pushed by a broker). Nothing here is presented as a push feed.

Frames: `hello` (transport contract), `audit` (one event, with `id` for resumption), `more` (a full batch, poll again), `heartbeat`, and `close` (reason + elapsed).

Guarantees:

- **Resumable without gaps or duplicates.** Send `last_event_id` (or the `Last-Event-ID` header) to receive only what you missed. The cursor keys on `(created_at, id)`, because two events can share a timestamp and a timestamp-only cursor silently drops one at the boundary — covered by a test that inserts three events with an identical timestamp.
- **Bounded lifetime** (`max_seconds`, default 300, max 300). Streams that outlive their client leak sessions and look healthy while dead. The server ends with an explicit `close` frame rather than vanishing.
- **Heartbeat** every `heartbeat_seconds` (5–60), so an idle connection is distinguishable from a stuck one.
- **Own database session.** The request session is closed when the response begins, so the generator builds its own factory; a generator holding the request session fails mid-stream.
- **Bounded batches** of 200 events per poll.
- **Same authentication as every other endpoint.** With `AATM_AUTH_MODE=token` the stream requires the bearer header; a token passed as a query parameter is rejected, because URLs land in logs and shell history. The dev proxy injects the header server-side, which is what lets the browser's `EventSource` (which cannot set headers) authenticate.

## Local task execution (opt-in)

Execution is **off by default**. `POST /orchestrator/run` returns **409** unless `AATM_EXECUTION_ENABLED` is set to `1`/`true`/`yes`/`on`; `GET /orchestrator/status` reports `executor.configured` and, when enabled, `enabled_by` and the active `allowed_programs`.

When enabled, one bounded batch runs through `LocalProcessExecutor` (`backend/app/execution.py`).

### Where the command comes from

A task names a command; it does not contain one. The name appears as an acceptance criterion `run:<name>`, and the argv for that name lives in `.aatm/exec.json` inside the project's isolated workspace — a file a human committed. **Executing a command string from the database would turn every task title into remote code execution**, so that is not supported.

```json
{ "report": { "argv": ["python3", "-m", "pytest", "-q"], "timeout_seconds": 120 } }
```

### Safety rules (each with a test)

| Rule | Why |
|---|---|
| No shell; argv lists only | no globbing, pipes or redirection |
| `argv[0]` must be a bare, allow-listed program | a path like `./evil` or `/bin/sh` is refused |
| cwd must be inside the registered workspace | `..` cannot escape it |
| Child inherits only `PATH`, `LANG`, `LC_ALL`, `TZ` | provider keys and `AATM_*` secrets never leak |
| Wall-clock timeout; process group killed | grandchildren are not orphaned |
| Output capped (64 KB default) | reported as `truncated`, never silently cut |
| Cancellation polled while running | a cancelled task is recorded as `cancelled`, not `failed` |
| Every live process registered | application shutdown terminates them |

A non-zero exit is a failure with evidence, not a success. A task that returns no evidence cannot complete.

### Two bugs found while building this

- **Cancellation could never reach a running task.** The orchestrator held an open write transaction for the whole subprocess run, so an operator's cancel request failed with `database is locked`. Fixed by committing the claim before executing (and enabling SQLite WAL). This was a real production defect, not a test artefact.
- **`expire_on_commit=False` left `cancel_requested_at` stale** in memory, so `honour_cancel` saw "no pending request" and a stopped task stayed in `running` forever. Fixed with an explicit refresh.

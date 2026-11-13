# AATM API Documentation

## Status and security

This API implements a Phase 1 local data foundation. It does not call AI providers or execute tasks. It is intended for loopback use and has no multi-user authentication; do not expose it to an untrusted network. The Vite UI sends relative `/api/v1` requests through its development proxy.

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

A created unassigned task starts `pending`; one created with an agent starts `assigned`. This API persists task metadata only; it does not schedule, execute, review, retry, or complete tasks. Dependency IDs must refer to existing tasks.

Priorities are `low`, `normal`, `high`, or `urgent`. State values are reserved for the planned workflow engine; no task execution endpoint exists in this foundation build.

### Audit events

- `GET /events?limit=100`

The initial audit trail records manager initialization, project/agent/task creation, and assignment changes. This is not yet a complete security audit system.

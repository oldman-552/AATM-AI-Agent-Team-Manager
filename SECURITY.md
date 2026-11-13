# Security Notes

## Current security posture

AATM is a local development foundation, not a production-ready multi-user service. It supports optional single-user local token authentication and blocks cross-origin state changes, but it has no user accounts, roles, or per-project authorization. Do not expose the backend to an untrusted network.

## Implemented baseline

- Backend and normal shell/PowerShell startup defaults bind to `127.0.0.1`.
- Backend uses Trusted Host middleware and a restrictive local CORS allowlist.
- Browser-facing UI requests use relative `/api/v1` paths; the development server proxies to the backend.
- No provider keys, cookies, or browser credentials are included in the frontend.
- `.env`, local data, SQLite databases, logs, Python environments, and browser-profile directories are ignored by Git.
- Progress reporter atomically replaces status files and redacts common inline credential labels before writing events.
- SQLite foreign-key checking is enabled.
- **Local authentication (opt-in):** `AATM_AUTH_MODE=token` requires a bearer token on every `/api/v1` request (health stays public). The comparison is constant-time, failures never echo the token, and starting in token mode without `AATM_AUTH_TOKEN` fails closed.
- **No secret in the browser:** the token lives in the Vite process and is injected into proxied requests server-side. A bundle scan confirms the token never appears in `web/src` or `web/dist`.
- **CSRF hardening:** mutating requests carrying a foreign `Origin` are rejected with 403 even when token mode is off, so a malicious page cannot drive the loopback API.
- Provider configuration stores **references only** (`env:NAME`, `keyring:service/account`). Raw keys are rejected at the schema boundary (extra fields forbidden), and credential values are never persisted, logged, or returned by any endpoint.
- Resolved credential values are redacted from provider error messages before they reach a caller (`redact_secrets`).
- Provider health, routing, and budget evaluation are offline: no HTTP route can trigger a live provider request, and `live_requests_allowed` is hard-coded `false` for the API.
- Arena integration is hard-blocked at the adapter and API level (409 on any enabling change); the blocked design is documented in `PROVIDER_RESEARCH.md`.
- Paid usage fails closed: no positive budget limit means no paid request, and explicit per-request consent is mandatory.
- Task state changes are validated server-side and recorded with append-only history and audit events; replayed idempotency keys cannot duplicate effects.
- Dedicated tests assert untrusted `Host` rejection (400) and that a hostile `Origin` receives no CORS allow header.

## Known gaps

- No user accounts, roles, per-project authorization, session management, rate limiting, encrypted credential vault, project-level filesystem sandbox, or network egress policy yet. Audit events are not yet attributed to an authenticated principal (local token mode has a single principal).
- The local token is a single shared secret; rotating it requires restarting both processes. `keyring:` references fail closed when no OS backend is available; Windows keyring behaviour is unverified.
- Budget enforcement depends on caller-supplied token estimates for preflight; live token counts can only diverge where an authorized in-process execution occurs.
- A local bind is not an authorization boundary against malicious software running as the same user.
- Vite is configured to allow the Arena preview domain suffix for hosted previews; normal local start scripts bind only to loopback.
- Provider and browser session integrations have not been implemented.

Never commit `.env`, API keys, passwords, browser profiles, database files, or private tokens. Do not bypass authentication, CAPTCHA, provider rate limits, or provider terms. Require approval for destructive actions, paid operations, protected-branch merges, and production deployment as those features are added.

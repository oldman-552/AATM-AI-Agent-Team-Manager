# Security Notes

## Current security posture

AATM is an early local development foundation, not a production-ready multi-user service. It has no user authentication or authorization. Do not expose the backend to an untrusted network.

## Implemented baseline

- Backend and normal shell/PowerShell startup defaults bind to `127.0.0.1`.
- Backend uses Trusted Host middleware and a restrictive local CORS allowlist.
- Browser-facing UI requests use relative `/api/v1` paths; the development server proxies to the backend.
- No provider keys, cookies, or browser credentials are included in the frontend.
- `.env`, local data, SQLite databases, logs, Python environments, and browser-profile directories are ignored by Git.
- Progress reporter atomically replaces status files and redacts common inline credential labels before writing events.
- SQLite foreign-key checking is enabled.

## Known gaps

- No application authentication/authorization, CSRF policy, encrypted credential vault, keyring integration, project-level filesystem sandbox, network egress policy, or complete audit trail exists yet.
- A local bind is not an authorization boundary against malicious software running as the same user.
- Vite is configured to allow the Arena preview domain suffix for hosted previews; normal local start scripts bind only to loopback.
- Provider and browser session integrations have not been implemented.

Never commit `.env`, API keys, passwords, browser profiles, database files, or private tokens. Do not bypass authentication, CAPTCHA, provider rate limits, or provider terms. Require approval for destructive actions, paid operations, protected-branch merges, and production deployment as those features are added.

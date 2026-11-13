# Configuration

## Runtime configuration available in the Phase 1 foundation

The backend uses Pydantic Settings and reads a `.env` file from its process working directory. `scripts/start.*` runs from the repository root. The supported initial settings are:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Backend bind address. Keep loopback for local use. |
| `PORT` | `8000` | Backend port used by the start scripts. |
| `DATABASE_URL` | SQLite under `~/.aatm/aatm.db` | SQLAlchemy database URL. SQLite parent folders are created automatically. |
| `CORS_ORIGINS` | `http://localhost:5173`, `http://127.0.0.1:5173` | JSON list of allowed browser origins. |
| `ALLOWED_HOSTS` | `localhost`, `127.0.0.1`, `[::1]`, `testserver` | Trusted Host middleware allowlist. Use a JSON list if changing it. |
| `AATM_HOME` | `~/.aatm` | Process environment override for the default SQLite data directory, used when `DATABASE_URL` is not set. |
| `AATM_UI_HOST` | `127.0.0.1` in start scripts | Vite bind address in shell/PowerShell startup scripts. |
| `AATM_UI_PORT` | `5173` in start scripts | Vite port. |

Copy `.env.example` to `.env` only if you need to override defaults. `.env` is ignored by Git. Never put credentials in Vite `VITE_*` variables or frontend files.

For PostgreSQL, install the included psycopg driver and use a SQLAlchemy URL such as `postgresql+psycopg://user:password@host/database`; keep secret values in a protected local environment and do not log them. PostgreSQL has not been integration-tested yet.

## Provider settings

Arena and Anthropic provider configuration, secret storage, routing, model selection, usage tracking, and budgets do not exist yet. No credentials are needed for the current API/UI foundation. Future Claude API use must be explicitly authorized and budget-enforced; a Claude subscription is not the same as API billing.

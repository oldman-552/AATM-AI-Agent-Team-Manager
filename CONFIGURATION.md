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

| `AATM_AUTH_MODE` | `off` | `off` or `token`. In `token` mode every `/api/v1` request needs a bearer token. |
| `AATM_AUTH_TOKEN` | unset | The local bearer token. Required when `AATM_AUTH_MODE=token`; the server refuses to start otherwise. Never commit it. |
| `AATM_WORKSPACES_ROOT` | `$AATM_HOME/workspaces` | Root directory for per-project Git workspaces. Paths are validated to stay inside it. |
| `AATM_MODEL_PRICING` | built-in conservative default | JSON object of local cost estimates, for example `{"<model>": {"input_per_million_usd": 3.0, "output_per_million_usd": 15.0}}`. These are **estimates** used for budget enforcement, not official or confirmed prices. |

## Provider settings

Provider configuration, routing, budgets, and usage are managed through the API/UI and stored in the database — not in `.env`.

- `credential_ref` accepts only `env:NAME` or `keyring:service/account`. The secret value itself stays in the environment or the OS keyring and is never stored by AATM.
- Example: export `ANTHROPIC_API_KEY` in the process environment, then set `credential_ref` to `env:ANTHROPIC_API_KEY`.
- `base_url` is limited to `api.anthropic.com` or a loopback address.
- Arena cannot be enabled through configuration: the adapter is blocked and the API returns 409.

### Live execution is intentionally not exposed

`GET /api/v1/providers*` and `POST /api/v1/providers/route` never contact a provider. The Anthropic adapter can execute only from in-process code that passes an explicit authorization flag; `load_settings()` forces `live_requests_allowed=False` for the HTTP application. Enabling real provider traffic is a deliberate future change that must add authorization, consent UX, and verified budget tests first.

### Enabling local authentication

```bash
export AATM_AUTH_MODE=token
export AATM_AUTH_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
scripts/start.sh   # start.sh passes the token to Vite so the proxy can inject it
```

Direct API calls then need `-H "Authorization: Bearer $AATM_AUTH_TOKEN"`. The UI keeps working because the token never leaves the Node proxy process. A local reverse proxy or port-forward that exposes the API should always run in token mode.

### Billing reality

Claude API usage is billed separately from a Claude subscription. AATM currently records only **local cost estimates** (`billing_status="estimated"`); it does not call any provider billing API and cannot confirm charges. No paid request can occur from the HTTP API in this build. Paid usage requires (a) an explicitly enabled provider, (b) a resolvable credential reference, (c) a positive budget limit, and (d) explicit per-request consent.

## Browser profile settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `AATM_BROWSER_PROFILES_ROOT` | `$AATM_HOME/browser-profiles` | Root for per-profile directories. Each profile gets `<root>/<uuid>` and can never escape this root. |

AATM does not launch a browser, so a profile directory is empty until some other tool writes to it. Cookies and login state are never read by AATM.

## Backup settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `AATM_BACKUP_DIR` | `$AATM_HOME/backups` | Where `scripts/backup.py` writes backups and manifests. |
| `DATABASE_URL` | `sqlite:///~/.aatm/aatm.db` | The database that backup/restore operates on. Only SQLite is supported by the bundled tool. |

See `BACKUP_AND_RESTORE.md` for the full procedure and safety properties.

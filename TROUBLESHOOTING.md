# Troubleshooting

## Installer says Python or Node is missing

Install Python 3.11+ and Node.js 20+ with npm, then rerun the platform-specific install script. The installer creates `.venv` and `web/node_modules` locally; both are ignored by Git.

## UI shows API unavailable

Start both services with `scripts/start.sh` (Linux/macOS) or `scripts/start.ps1` (Windows), then visit `http://127.0.0.1:5173`. Check `.aatm/logs/backend.log` and `.aatm/logs/frontend.log` on Linux, or the corresponding `*-error.log` files on Windows. The browser UI uses the Vite `/api` proxy; do not point it at browser-side `localhost` URLs.

## Database startup/migration errors

Check `DATABASE_URL`, ensure its parent directory is writable, and inspect the backend log. Alembic migrations run when the API starts. Keep a backup before modifying a database manually. The current default is SQLite; PostgreSQL has not been integration-tested.

## Port already in use

Set `PORT` and/or `AATM_UI_PORT` before starting. Use the stop script for processes recorded by AATM; do not kill unrelated processes by guessed PID.

## Docker command unavailable

Docker is optional for the current local SQLite development setup.

## Windows verification

Windows scripts cannot be executed from the current Linux environment. Passing shell-script checks does not prove PowerShell scripts work. See `BLOCKERS.txt`.

## The UI URL printed by `scripts/start.sh` does not load

The script now verifies the UI actually responds before printing a URL. If you see:

```
ERROR: the UI did not start on port 5173 (usually the port is busy).
```

another process holds the port. Either stop it or start AATM elsewhere:

```bash
AATM_UI_PORT=5174 scripts/start.sh
```

The frontend log is at `.aatm/logs/frontend.log`; look for `Port ... is already in use`.

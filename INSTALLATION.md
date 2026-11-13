# Installation and Local Development

## Status

The scripts below provide a starter local development path; this is not yet a release installer. The intended targets are Ubuntu Desktop 24.04+ and Windows 11. Linux commands are executable in the current environment. PowerShell scripts have not yet been run on Windows and are not marked verified.

## Prerequisites

- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- Git for source updates.
- Docker is not required for SQLite development.

## Ubuntu/Linux

```bash
scripts/install.sh
scripts/start.sh
# Browse to http://127.0.0.1:5173
scripts/stop.sh
```

The API defaults to `127.0.0.1:8000`; Vite defaults to `127.0.0.1:5173` in the start script. Runtime logs and PID files are under `.aatm/` (ignored by Git).

## Windows 11 PowerShell

From the repository root:

```powershell
.\scripts\install.ps1
.\scripts\start.ps1
# Browse to http://127.0.0.1:5173
.\scripts\stop.ps1
```

The installer checks for Python 3.11+ and Node.js 20+. This script path needs actual Windows 11 verification before release.

## Database and data location

The default database is file-backed SQLite at `~/.aatm/aatm.db` (the user's home directory). Set `AATM_HOME` in the process environment to change the default directory, or set `DATABASE_URL` in `.env` to an explicit SQLAlchemy URL. Example for a project-local development database:

```dotenv
DATABASE_URL=sqlite:///./.aatm/aatm.db
```

The parent folder is created automatically. Alembic migrations run during API startup. PostgreSQL can be configured with a `postgresql+psycopg://...` URL, but no PostgreSQL server integration test has been run.

## Updating

The `scripts/update.sh` and `scripts/update.ps1` procedures require a clean working tree. They perform a fast-forward-only pull from the current configured branch and then reinstall/synchronize dependencies. Review the source and backup important local data before updating. They never force-reset the working tree.

## Uninstalling

The uninstall scripts stop the local services and remove only the generated Python virtual environment, frontend dependencies, and frontend build output. They intentionally preserve source code, `.aatm/` runtime data/database/logs, `.env`, and Git history. Remove user data manually only after taking a backup and confirming the target path.

## Not yet included

There is not yet a signed installer, desktop service manager, automatic update mechanism, secure OS credential integration, browser profile manager, release packaging, or tested backup/restore utility. Do not expose the development API to an untrusted network.

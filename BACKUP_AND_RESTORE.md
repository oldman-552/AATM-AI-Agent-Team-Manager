# Backup and Restore

## Status

A supported backup/restore command, encryption, retention, and validation workflow are **not implemented**. Do not rely on the application as the sole copy of project data.

The default SQLite file is under `~/.aatm/aatm.db`; if `DATABASE_URL` is configured, use that exact database location. A configured PostgreSQL database is managed externally. The app may be running while data changes, so do not copy a live SQLite database file as if it were a transactionally consistent backup.

Until a supported backup tool exists, stop the AATM services and use a database-aware SQLite backup method for local data; store backups securely and test restores into a separate location before replacing live data. Never include credentials or browser authentication state in ordinary backups. Do not overwrite existing data without an explicit confirmation.

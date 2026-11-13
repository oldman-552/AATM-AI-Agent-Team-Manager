# Backup and Restore

## Status

A working local backup/restore command with verification and retention is **implemented and tested** for SQLite. Encryption of backup files and PostgreSQL backup orchestration are **not implemented**.

The default database is `~/.aatm/aatm.db` (or `$AATM_HOME/aatm.db`); with `DATABASE_URL` set, that exact path is used. A configured PostgreSQL database is managed externally by your own tooling.

## Why not `cp`?

Copying a live SQLite file can capture a half-written page. AATM uses SQLite's **online backup API**, which produces a transactionally consistent copy while the API keeps running.

## Commands

```bash
# Create a consistent backup (default: $AATM_HOME/backups, or $AATM_BACKUP_DIR)
scripts/backup.py create --name before-upgrade

# List backups with timestamps, sizes and hashes
scripts/backup.py list

# Verify the recorded SHA-256 and run PRAGMA integrity_check
scripts/backup.py verify --name before-upgrade

# Restore — requires BOTH flags, and the API should be stopped first
scripts/backup.py restore --name before-upgrade --allow-overwrite --yes

# Keep only the newest 5 backups
scripts/backup.py prune --keep 5
```

Every backup writes `<name>.sqlite3` plus `<name>.manifest.json` (source path, timestamp, byte size, SHA-256).

## Safety properties

- **No silent overwrite.** Restore refuses without `allow_overwrite=true`, and the CLI additionally requires `--yes`.
- **Verified before restore.** The SHA-256 must match the manifest and `PRAGMA integrity_check` must return `ok`; otherwise the restore is refused.
- **Previous database preserved.** The replaced file is copied to `<db>.pre-restore-<UTC>.sqlite3` before the restore, and copied back if the restored file fails its integrity check.
- **No path traversal.** Names are validated (`^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$`, no `..`), so a name cannot escape the backup directory.
- **Measured, not assumed.** After a restore the command re-opens the restored file, re-runs `integrity_check`, and counts rows.

## Operational guidance

1. Stop the API before restoring, then restart it so every process uses the restored file.
2. Verify a backup before you depend on it — a file that exists is not a file that restores.
3. Keep backups outside the repository; they can contain project data.
4. Backups never contain credentials by default: provider keys live in `env:`/`keyring:` references, not in the database. Do not add secrets to backups.
5. Test restores into a scratch `DATABASE_URL` before replacing real data.

## Not covered

- Encryption at rest for backup files; use your OS or an encrypted volume.
- Off-site/scheduled backups; automate `scripts/backup.py create` with cron or a systemd timer if needed.
- PostgreSQL logical dumps; use `pg_dump`/`pg_restore` for those deployments.
- Browser-profile and workspace-directory backups; both live outside the database.

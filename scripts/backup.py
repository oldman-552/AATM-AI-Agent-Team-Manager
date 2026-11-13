#!/usr/bin/env python3
"""AATM backup/restore command line.

Examples:
    scripts/backup.py create --name before-upgrade
    scripts/backup.py list
    scripts/backup.py verify --name before-upgrade
    scripts/backup.py restore --name before-upgrade --allow-overwrite --yes
    scripts/backup.py prune --keep 5
"""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.backup import (  # noqa: E402
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
    verify_backup,
)


def default_backup_dir() -> Path:
    configured = os.environ.get("AATM_BACKUP_DIR")
    if configured:
        return Path(configured).expanduser()
    home = Path(os.environ.get("AATM_HOME", Path.home() / ".aatm")).expanduser()
    return home / "backups"


def database_url() -> str:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured
    from app.core.config import settings  # imported lazily so --help works without deps

    return settings.database_url


def main() -> int:
    parser = argparse.ArgumentParser(description="AATM local database backup and restore.")
    parser.add_argument("--backup-dir", type=Path, default=default_backup_dir())
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a consistent on-line backup.")
    create.add_argument("--name", default=None)

    commands.add_parser("list", help="List available backups.")

    verify = commands.add_parser("verify", help="Verify a backup's hash and integrity.")
    verify.add_argument("--name", required=True)

    restore = commands.add_parser("restore", help="Restore a verified backup.")
    restore.add_argument("--name", required=True)
    restore.add_argument("--allow-overwrite", action="store_true")
    restore.add_argument("--yes", action="store_true", help="Confirm the destructive restore.")

    prune = commands.add_parser("prune", help="Delete the oldest backups beyond --keep.")
    prune.add_argument("--keep", type=int, default=5)

    args = parser.parse_args()
    try:
        if args.command == "create":
            info = create_backup(database_url(), args.backup_dir, name=args.name)
            print(f"Created backup {info.name} ({info.size_bytes} bytes, sha256 {info.sha256[:16]}…)")
        elif args.command == "list":
            backups = list_backups(args.backup_dir)
            if not backups:
                print("No backups found.")
            for info in backups:
                print(f"{info.name}\t{info.created_at}\t{info.size_bytes} bytes\t{info.sha256[:16]}…")
        elif args.command == "verify":
            result = verify_backup(args.backup_dir, args.name)
            print(("OK   " if result["ok"] else "FAIL ") + ", ".join(result["checks"]))
            return 0 if result["ok"] else 1
        elif args.command == "restore":
            if not args.yes:
                print("Refusing to restore without --yes. Stop the API first, then re-run with --yes.", file=sys.stderr)
                return 2
            result = restore_backup(
                database_url(),
                args.backup_dir,
                args.name,
                allow_overwrite=args.allow_overwrite,
            )
            print(f"Restored {result['name']} into {result['target']}")
            if result["previous_copy"]:
                print(f"Previous database kept at {result['previous_copy']}")
            print(result["note"])
        elif args.command == "prune":
            removed = prune_backups(args.backup_dir, keep=args.keep)
            print(f"Removed {len(removed)} backup(s)." if removed else "Nothing to remove.")
    except BackupError as exc:
        print(f"Backup error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

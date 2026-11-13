"""Local backup and restore for the AATM SQLite database.

Guarantees:

* Backups use SQLite's online backup API, so a copy is consistent even while the
  application is running (no naive file copy of a live database).
* A manifest records the source path, timestamp, byte size and SHA-256, so a
  backup can be verified later instead of trusted blindly.
* Restore never overwrites silently: it refuses unless the target is explicitly
  allowed to be replaced, keeps a timestamped copy of the previous database,
  and verifies the restore by opening the restored file and running
  ``PRAGMA integrity_check`` plus a real query.
* Only local filesystem paths inside the configured backup directory are read
  or written; archive names are validated so ``../`` cannot escape.
"""

import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


class BackupError(RuntimeError):
    """A safe, user-facing backup/restore failure."""


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    size_bytes: int
    created_at: str
    sha256: str
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "sha256": self.sha256,
            "source": self.source,
        }


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise BackupError("Backup is implemented for SQLite databases only in this build.")
    return Path(database_url.replace("sqlite:///", "", 1)).expanduser().resolve()


def validate_name(name: str) -> str:
    if not NAME_PATTERN.fullmatch(name or "") or ".." in name:
        raise BackupError("Backup names may only contain letters, digits, '.', '_' and '-'.")
    return name


def create_backup(
    database_url: str,
    backup_dir: Path,
    *,
    name: str | None = None,
) -> BackupInfo:
    """Create a consistent on-line backup plus a manifest."""
    source_path = sqlite_path_from_url(database_url)
    if not source_path.exists():
        raise BackupError("The database file does not exist yet; start the application once first.")
    backup_dir = Path(backup_dir).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    if name is not None and not name.strip():
        raise BackupError("A backup name cannot be blank.")
    backup_name = name or f"aatm-{_utc_stamp()}"
    validate_name(backup_name)
    target = (backup_dir / f"{backup_name}.sqlite3")
    if target.exists():
        raise BackupError("A backup with that name already exists.")

    source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        destination = sqlite3.connect(str(target))
        try:
            source_connection.backup(destination)
            destination.execute("PRAGMA integrity_check").fetchone()
        finally:
            destination.close()
    finally:
        source_connection.close()

    info = BackupInfo(
        name=backup_name,
        path=target,
        size_bytes=target.stat().st_size,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sha256=_sha256(target),
        source=str(source_path),
    )
    (backup_dir / f"{backup_name}.manifest.json").write_text(
        json.dumps({"backup": info.as_dict()}, indent=2) + "\n", encoding="utf-8"
    )
    return info


def list_backups(backup_dir: Path) -> list[BackupInfo]:
    directory = Path(backup_dir).expanduser().resolve()
    if not directory.exists():
        return []
    results: list[BackupInfo] = []
    for manifest in sorted(directory.glob("*.manifest.json")):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))["backup"]
            path = directory / f"{payload['name']}.sqlite3"
            if not path.exists():
                continue
            results.append(
                BackupInfo(
                    name=str(payload["name"]),
                    path=path,
                    size_bytes=int(payload["size_bytes"]),
                    created_at=str(payload["created_at"]),
                    sha256=str(payload["sha256"]),
                    source=str(payload.get("source", "")),
                )
            )
        except (OSError, KeyError, ValueError, TypeError):
            continue
    return sorted(results, key=lambda item: item.created_at, reverse=True)


def verify_backup(backup_dir: Path, name: str) -> dict[str, object]:
    """Check the recorded hash, then open the backup and run integrity_check."""
    directory = Path(backup_dir).expanduser().resolve()
    validate_name(name)
    path = directory / f"{name}.sqlite3"
    manifest = directory / f"{name}.manifest.json"
    if not path.exists() or not manifest.exists():
        raise BackupError("Backup or manifest not found.")
    expected = str(json.loads(manifest.read_text(encoding="utf-8"))["backup"]["sha256"])
    actual = _sha256(path)
    checks: list[str] = []
    ok = actual == expected
    checks.append("sha256 matches manifest" if ok else "sha256 MISMATCH")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            integrity_value = str(integrity[0]) if integrity else "unknown"
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
        finally:
            connection.close()
        checks.append(f"integrity_check: {integrity_value}")
        ok = ok and integrity_value == "ok"
    except sqlite3.DatabaseError as exc:
        # A tampered or truncated file is a verification failure, not a crash.
        return {
            "name": name,
            "ok": False,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "tables": [],
            "checks": checks + [f"not a readable SQLite database: {type(exc).__name__}"],
        }
    return {
        "name": name,
        "ok": ok,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "tables": tables,
        "checks": checks,
    }


def restore_backup(
    database_url: str,
    backup_dir: Path,
    name: str,
    *,
    allow_overwrite: bool = False,
) -> dict[str, object]:
    """Restore a verified backup, preserving the previous database first."""
    if not allow_overwrite:
        raise BackupError("Restore requires allow_overwrite=true; existing data is never replaced silently.")
    verification = verify_backup(backup_dir, name)
    if not verification["ok"]:
        raise BackupError("Backup verification failed; refusing to restore.")

    target = sqlite_path_from_url(database_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    previous_copy: Path | None = None
    if target.exists():
        previous_copy = target.with_name(f"{target.stem}.pre-restore-{_utc_stamp()}{target.suffix}")
        shutil.copy2(target, previous_copy)

    shutil.copy2(Path(backup_dir) / f"{name}.sqlite3", target)

    connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        integrity_value = str(integrity[0]) if integrity else "unknown"
        agent_count = connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    finally:
        connection.close()
    if integrity_value != "ok":
        if previous_copy is not None:
            shutil.copy2(previous_copy, target)
        raise BackupError("Restored database failed its integrity check; the previous database was put back.")

    return {
        "restored": True,
        "name": name,
        "target": str(target),
        "previous_copy": str(previous_copy) if previous_copy else None,
        "integrity_check": integrity_value,
        "agent_rows": int(agent_count),
        "note": "Restart the API to ensure every process uses the restored database file.",
    }


def prune_backups(backup_dir: Path, keep: int = 5) -> list[str]:
    """Delete the oldest backups beyond ``keep`` (manifest + database together)."""
    if keep < 1:
        raise BackupError("Keep at least one backup.")
    backups = list_backups(backup_dir)
    removed: list[str] = []
    for info in backups[keep:]:
        try:
            (Path(backup_dir) / f"{info.name}.sqlite3").unlink(missing_ok=True)
            (Path(backup_dir) / f"{info.name}.manifest.json").unlink(missing_ok=True)
            removed.append(info.name)
        except OSError:
            continue
    return removed

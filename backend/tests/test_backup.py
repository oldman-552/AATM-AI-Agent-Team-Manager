"""Backup, verification, restore and pruning against real SQLite files."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backup import (
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
    verify_backup,
)
from app.main import create_app


@pytest.fixture
def database_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"


def seed(database_url: str, name: str = "Backed up project") -> None:
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as client:
        assert client.post("/api/v1/projects", json={"name": name}).status_code == 201


def test_backup_verify_and_restore_round_trip(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    info = create_backup(database_url, backups, name="snapshot-1")
    assert info.path.exists()
    assert info.size_bytes > 0
    assert len(info.sha256) == 64

    listed = list_backups(backups)
    assert [item.name for item in listed] == ["snapshot-1"]

    verification = verify_backup(backups, "snapshot-1")
    assert verification["ok"] is True
    assert "agents" in verification["tables"]
    assert "projects" in verification["tables"]

    # Mutate live data, then restore and confirm the old state returns.
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as client:
        assert client.post("/api/v1/projects", json={"name": "Added later"}).status_code == 201
        assert len(client.get("/api/v1/projects").json()) == 2

    restored = restore_backup(database_url, backups, "snapshot-1", allow_overwrite=True)
    assert restored["restored"] is True
    assert restored["integrity_check"] == "ok"
    assert Path(restored["previous_copy"]).exists()  # safety copy of the replaced database

    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as client:
        projects = client.get("/api/v1/projects").json()
        assert [project["name"] for project in projects] == ["Backed up project"]


def test_restore_requires_explicit_overwrite(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    create_backup(database_url, backups, name="snap")
    with pytest.raises(BackupError, match="allow_overwrite"):
        restore_backup(database_url, backups, "snap")


def test_names_are_validated_and_cannot_escape(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    for bad in ("../escape", "a/b", "", "..", "x" * 200):
        with pytest.raises(BackupError):
            create_backup(database_url, backups, name=bad)
    assert not list(backups.glob("*.sqlite3")) if backups.exists() else True
    with pytest.raises(BackupError):
        verify_backup(backups, "../escape")


def test_duplicate_names_are_rejected(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    create_backup(database_url, backups, name="same")
    with pytest.raises(BackupError, match="already exists"):
        create_backup(database_url, backups, name="same")


def test_tampered_backup_fails_verification_and_restore(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    create_backup(database_url, backups, name="tamper")
    target = backups / "tamper.sqlite3"
    target.write_bytes(b"not a real database")
    verification = verify_backup(backups, "tamper")
    assert verification["ok"] is False
    assert any("MISMATCH" in check for check in verification["checks"])
    with pytest.raises(BackupError, match="verification failed"):
        restore_backup(database_url, backups, "tamper", allow_overwrite=True)


def test_missing_database_and_non_sqlite_urls_are_rejected(tmp_path) -> None:
    with pytest.raises(BackupError, match="does not exist"):
        create_backup(f"sqlite:///{(tmp_path / 'missing.sqlite3').as_posix()}", tmp_path / "b")
    seed(f"sqlite:///{(tmp_path / 'real.sqlite3').as_posix()}")
    with pytest.raises(BackupError, match="SQLite"):
        create_backup("postgresql+psycopg://user@host/db", tmp_path / "b")


def test_prune_keeps_the_newest_entries(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    for index in range(4):
        create_backup(database_url, backups, name=f"snap-{index}")
        import time
        time.sleep(1.05)  # created_at has second resolution
    removed = prune_backups(backups, keep=2)
    assert len(removed) == 2
    remaining = [item.name for item in list_backups(backups)]
    assert remaining == ["snap-3", "snap-2"]
    with pytest.raises(BackupError):
        prune_backups(backups, keep=0)


def test_backup_of_live_database_is_consistent(tmp_path, database_url) -> None:
    seed(database_url)
    backups = tmp_path / "backups"
    # Take the backup while the application holds an open connection.
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as client:
        info = create_backup(database_url, backups, name="live")
        assert client.get("/api/v1/health").json()["status"] == "ok"
    connection = sqlite3.connect(f"file:{info.path}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    finally:
        connection.close()

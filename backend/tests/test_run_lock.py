from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.run_lock import acquire_run_lock, release_run_lock, renew_run_lock

UTC = timezone.utc


@pytest.fixture
def client(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'endpoint.sqlite3').as_posix()}"
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as test_client:
        yield test_client


def test_database_run_lock_is_shared_expires_and_is_owner_checked(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'shared.sqlite3').as_posix()}"
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as first_client:
        with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as second_client:
            instant = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
            first_db = first_client.app.state.session_factory()
            second_db = second_client.app.state.session_factory()
            try:
                assert acquire_run_lock(first_db, "process-a", lease_seconds=10, now=instant)
                assert not acquire_run_lock(second_db, "process-b", lease_seconds=10, now=instant + timedelta(seconds=5))
                assert renew_run_lock(first_db, "process-a", lease_seconds=10, now=instant + timedelta(seconds=5))
                assert not acquire_run_lock(second_db, "process-b", lease_seconds=10, now=instant + timedelta(seconds=11))
                assert acquire_run_lock(second_db, "process-b", lease_seconds=10, now=instant + timedelta(seconds=16))
                assert not renew_run_lock(first_db, "process-a", lease_seconds=10, now=instant + timedelta(seconds=16))
                assert not release_run_lock(first_db, "process-a")
                assert release_run_lock(second_db, "process-b")
            finally:
                first_db.close()
                second_db.close()


def test_run_endpoint_rejects_a_run_owned_by_another_api_process(client, monkeypatch) -> None:
    monkeypatch.setenv("AATM_EXECUTION_ENABLED", "1")
    db = client.app.state.session_factory()
    try:
        assert acquire_run_lock(db, "another-api-process", lease_seconds=120)
    finally:
        db.close()

    response = client.post("/api/v1/orchestrator/run")
    assert response.status_code == 409
    assert "already active for this database" in response.json()["detail"]

    db = client.app.state.session_factory()
    try:
        assert release_run_lock(db, "another-api-process")
    finally:
        db.close()


def test_successful_run_endpoint_releases_database_lock(client, monkeypatch) -> None:
    monkeypatch.setenv("AATM_EXECUTION_ENABLED", "1")
    response = client.post("/api/v1/orchestrator/run")
    assert response.status_code == 200

    db = client.app.state.session_factory()
    try:
        assert acquire_run_lock(db, "next-run", lease_seconds=120)
        assert release_run_lock(db, "next-run")
    finally:
        db.close()

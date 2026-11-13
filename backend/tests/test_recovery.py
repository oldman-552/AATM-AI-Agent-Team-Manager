"""Self-healing and recovery: real detection, honest capability claims."""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db import safe_close
from app.main import create_app
from app.recovery import classify_database_error, is_transient


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def test_recovery_report_distinguishes_automatic_from_advisory(client: TestClient) -> None:
    report = client.get("/api/v1/recovery").json()
    db = report["database"]
    assert db["ok"] is True and db["category"] == "ok"
    assert db["integrity"] == {"ok": True, "result": "ok"}
    assert db["elapsed_ms"] >= 0

    caps = {item["failure"]: item for item in report["capabilities"]}
    # The only genuinely automatic recoveries are lease reclaim and restart survival.
    automatic = {name for name, item in caps.items() if item["automatic"]}
    assert automatic == {"Agent crash / interrupted task", "Application or OS restart"}
    # Browser and provider failures must be reported as not applicable, not "handled".
    assert caps["Browser crash"]["handled"] is False
    assert caps["Provider or network failure"]["handled"] is False
    assert set(report["summary"]["not_applicable"]) == {"Browser crash", "Provider or network failure"}
    assert report["summary"]["detected"] == 5
    assert "duplicate an external effect" in report["idempotency"]


def test_queue_health_reports_real_counts(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Recovery"}).json()
    agent = client.post("/api/v1/agents", json={"name": "W", "role": "developer"}).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Failing", "project_id": project["id"], "assigned_agent_id": agent["id"]},
    ).json()
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "running", "idempotency_key": "r1", "note": "go"},
    )
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "failed", "idempotency_key": "r2", "note": "boom"},
    )

    queue = client.get("/api/v1/recovery").json()["queue"]
    assert queue["by_state"].get("failed") == 1
    assert queue["recoverable_tasks"] == 1     # retry_count 1 < ceiling
    assert queue["exhausted_tasks"] == 0
    assert queue["retry_ceiling"] == 3


def test_database_probe_endpoint_reports_timing(client: TestClient) -> None:
    body = client.get("/api/v1/recovery/database").json()
    assert body["ok"] is True
    assert isinstance(body["elapsed_ms"], float)
    assert body["slow"] is False


@pytest.mark.parametrize(
    ("exception", "category", "status_hint"),
    [
        (OperationalError("SELECT 1", {}, Exception("database is locked")), "locked", 409),
        (OperationalError("SELECT 1", {}, Exception("no such table: tasks")), "schema", 503),
        (OperationalError("SELECT 1", {}, Exception("file is not a database")), "corrupt", 503),
        (OperationalError("SELECT 1", {}, Exception("unable to open database file")), "unavailable", 503),
    ],
)
def test_database_errors_are_classified_with_actionable_advice(
    exception: Exception, category: str, status_hint: int
) -> None:
    detail = classify_database_error(exception)
    assert detail["category"] == category
    assert detail["advice"]
    assert detail["automatic_recovery"] is False
    assert "back" in detail["note"] and "transaction" in detail["note"]


def test_constraint_errors_are_not_mistaken_for_lock_contention() -> None:
    exc = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: tasks.title"))
    detail = classify_database_error(exc)
    assert detail["category"] == "constraint"
    assert is_transient(exc) is False


def test_only_lock_contention_is_treated_as_transient() -> None:
    assert is_transient(OperationalError("x", {}, Exception("database is locked"))) is True
    assert is_transient(sqlite3.OperationalError("database is locked")) is True
    assert is_transient(OperationalError("x", {}, Exception("no such table: tasks"))) is False
    # An integrity error would fail identically on retry, so retrying hides a defect.
    assert is_transient(IntegrityError("x", {}, Exception("FOREIGN KEY constraint failed"))) is False


def test_safe_close_rolls_back_an_open_transaction(client: TestClient) -> None:
    """A failed transaction must not leak into the next request on the pool."""
    factory = client.app.state.session_factory
    session = factory()
    from sqlalchemy import text

    session.execute(text("SELECT 1"))
    assert session.in_transaction() is True
    safe_close(session)
    assert not session.in_transaction()

    # The service is still healthy afterwards.
    assert client.get("/api/v1/health").status_code == 200


def test_health_reports_database_failure_instead_of_raising(client: TestClient) -> None:
    """If the database becomes unusable, /health says why; it does not 500 blindly."""
    from fastapi import Response

    from app.api import health

    class Exploding:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))

    request = type("Req", (), {"app": type("App", (), {"title": "AATM"})()})()
    response = Response()
    body = health(request, response, Exploding())

    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["database"]["category"] == "locked"
    assert body["database"]["advice"]


def test_health_endpoint_stays_200_when_database_is_fine(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"

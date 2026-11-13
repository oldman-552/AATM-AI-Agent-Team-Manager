"""Notifications must reflect real pending work and persist read state."""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Task as TaskModel


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def test_empty_state_has_no_notifications(client: TestClient) -> None:
    body = client.get("/api/v1/notifications").json()
    assert body["notifications"] == []
    assert body["unread"] == 0
    assert "no synthetic events" in body["source"]
    assert client.post("/api/v1/notifications/read-all").json()["marked_read"] == 0


def test_pending_approvals_become_notifications(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Notify"}).json()
    approval = client.post(
        "/api/v1/approvals",
        json={"kind": "deployment", "summary": "Deploy to staging", "entity_type": "project", "entity_id": project["id"]},
    ).json()["approval"]
    body = client.get("/api/v1/notifications").json()
    assert body["unread"] == 1
    item = body["notifications"][0]
    assert item["kind"] == "approval_pending"
    assert item["message_key"] == "notificationApprovalPending"
    assert item["entity_id"] == project["id"]
    assert item["action_view"] == "approvals"
    assert item["read"] is False
    assert item["data"]["summary"] == "Deploy to staging"

    # Deciding the approval removes the notification, because it is derived.
    decided = client.patch(
        f"/api/v1/approvals/{approval['id']}",
        json={"status": "approved", "decided_by": "owner"},
    )
    assert decided.status_code == 200, decided.text
    assert client.get("/api/v1/notifications").json()["notifications"] == []


def test_read_state_persists_across_restart(client: TestClient, tmp_path) -> None:
    client.post(
        "/api/v1/approvals",
        json={"kind": "data_deletion", "summary": "Delete old rows", "entity_type": "task"},
    )
    notification_id = client.get("/api/v1/notifications").json()["notifications"][0]["id"]
    marked = client.post("/api/v1/notifications/read", json={"ids": [notification_id]}).json()
    assert marked["marked_read"] == 1
    assert marked["unread"] == 0

    url = client.app.state.engine.url.render_as_string(hide_password=False)
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as restarted:
        body = restarted.get("/api/v1/notifications").json()
        assert body["unread"] == 0
        assert body["notifications"][0]["read"] is True
        assert body["notifications"][0]["read_at"] is not None


def test_failed_and_rework_tasks_are_reported(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Tasks"}).json()
    agent = client.post(
        "/api/v1/agents", json={"name": "Dev", "role": "developer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks", json={"title": "Broken job", "project_id": project["id"], "assigned_agent_id": agent["id"]}
    ).json()
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "running", "idempotency_key": "s1", "note": "go"},
    )
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "failed", "idempotency_key": "s2", "note": "compile error", "error": "E1"},
    )
    items = client.get("/api/v1/notifications").json()["notifications"]
    failing = [item for item in items if item["kind"] == "task_needs_attention"]
    assert failing and failing[0]["message_key"] == "notificationTaskFailing"
    assert failing[0]["severity"] == "error"
    assert failing[0]["data"]["title"] == "Broken job"
    assert failing[0]["action_view"] == "tasks"


def test_expired_lease_is_reported_and_live_lease_is_not(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Leases"}).json()
    agent = client.post(
        "/api/v1/agents", json={"name": "Worker", "role": "developer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks", json={"title": "Long run", "project_id": project["id"], "assigned_agent_id": agent["id"]}
    ).json()
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "running", "idempotency_key": "l1", "note": "start"},
    )

    def set_lease(delta_minutes: int) -> None:
        with Session(client.app.state.engine) as session:
            row = session.scalar(select(TaskModel).where(TaskModel.id == task["id"]))
            row.lease_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=delta_minutes)
            session.commit()

    set_lease(10)
    assert not [item for item in client.get("/api/v1/notifications").json()["notifications"] if item["kind"] == "lease_expired"]
    set_lease(-10)
    expired = [item for item in client.get("/api/v1/notifications").json()["notifications"] if item["kind"] == "lease_expired"]
    assert expired and expired[0]["message_key"] == "notificationLeaseExpired"


def test_validation_and_retention(client: TestClient) -> None:
    assert client.post("/api/v1/notifications/read", json={"ids": []}).status_code == 422
    assert client.post("/api/v1/notifications/read", json={"ids": ["no-separator"]}).status_code == 422
    assert client.post("/api/v1/notifications/read", json={"ids": ["approval:missing"]}).json()["marked_read"] == 1
    assert client.delete("/api/v1/notifications/read-state", params={"older_than_days": 0}).status_code == 422
    # Default retention keeps fresh read state; only expired rows are pruned.
    assert client.delete("/api/v1/notifications/read-state").json()["removed"] == 0


def test_read_all_is_idempotent(client: TestClient) -> None:
    client.post("/api/v1/approvals", json={"kind": "deployment", "summary": "One"})
    client.post("/api/v1/approvals", json={"kind": "deployment", "summary": "Two"})
    first = client.post("/api/v1/notifications/read-all").json()
    assert first["marked_read"] == 2
    assert first["unread"] == 0
    second = client.post("/api/v1/notifications/read-all").json()
    assert second["marked_read"] == 0

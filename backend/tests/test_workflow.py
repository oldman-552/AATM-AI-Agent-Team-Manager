"""Tests for the local task state machine, dependency gates and replay safety."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        "sqlite://",
        allowed_origins=["http://localhost:5173"],
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
    )
    with TestClient(app) as test_client:
        yield test_client


def create_agent(client: TestClient, name: str = "Worker") -> str:
    return client.post("/api/v1/agents", json={"name": name, "role": "QA Engineer"}).json()["id"]


def create_task(client: TestClient, **payload) -> dict:
    body = {"title": "Verify workflow"}
    body.update(payload)
    response = client.post("/api/v1/tasks", json=body)
    assert response.status_code == 201
    return response.json()


def change(client: TestClient, task_id: str, target_state: str, key: str, **extra):
    payload = {"target_state": target_state, "idempotency_key": key}
    payload.update(extra)
    return client.patch(f"/api/v1/tasks/{task_id}/state", json=payload)


def test_transitions_are_validated_audited_and_idempotent(client: TestClient) -> None:
    agent = create_agent(client)
    task = create_task(client, assigned_agent_id=agent)
    assert task["state"] == "assigned"

    started = change(client, task["id"], "running", "start-1")
    assert started.status_code == 200
    assert started.json()["task"]["state"] == "running"
    assert started.json()["transition_created"] is True
    assert "completed" in started.json()["allowed_next_states"]

    replay = change(client, task["id"], "running", "start-1")
    assert replay.status_code == 200
    assert replay.json()["transition_created"] is False

    history = client.get(f"/api/v1/tasks/{task['id']}/transitions").json()["transitions"]
    assert len(history) == 1
    assert history[0]["from_state"] == "assigned" and history[0]["to_state"] == "running"

    events = client.get("/api/v1/events").json()
    assert len([event for event in events if event["event_type"] == "task.state_changed"]) == 1

    invalid = change(client, task["id"], "approved", "bad-1")
    assert invalid.status_code == 409
    assert "not allowed" in invalid.json()["detail"]

    conflicting_key = change(client, task["id"], "completed", "start-1")
    assert conflicting_key.status_code == 409

    needs_evidence = change(client, task["id"], "failed", "fail-1")
    assert needs_evidence.status_code == 409
    assert "Evidence" in needs_evidence.json()["detail"]

    failed = change(client, task["id"], "failed", "fail-1", note="Test suite failed", error="assertion error")
    assert failed.status_code == 200
    assert failed.json()["task"]["retry_count"] == 1
    assert failed.json()["task"]["error"] == "assertion error"

    rework = change(client, task["id"], "rework_required", "rework-1", note="Requires fix")
    assert rework.status_code == 200
    assert rework.json()["task"]["retry_count"] == 2


def test_dependencies_gate_starting_and_ready_queue(client: TestClient) -> None:
    agent = create_agent(client)
    first = create_task(client, title="Foundation task", assigned_agent_id=agent)
    second = create_task(
        client,
        title="Dependent task",
        assigned_agent_id=agent,
        dependencies=[first["id"]],
    )

    ready = client.get("/api/v1/tasks/ready").json()
    assert [item["id"] for item in ready["tasks"]] == [first["id"]]

    blocked = change(client, second["id"], "running", "dep-blocked")
    assert blocked.status_code == 409
    assert "Dependencies" in blocked.json()["detail"]

    assert change(client, first["id"], "running", "first-run").status_code == 200
    assert change(client, first["id"], "completed", "first-done").status_code == 200

    ready_after = client.get("/api/v1/tasks/ready").json()
    assert {item["id"] for item in ready_after["tasks"]} == {second["id"]}
    assert change(client, second["id"], "running", "second-run").status_code == 200


def test_terminal_states_and_unassigned_start_are_rejected(client: TestClient) -> None:
    unassigned = create_task(client, title="No owner")
    response = change(client, unassigned["id"], "running", "unassigned-run")
    assert response.status_code in (409, 422)  # cannot start from 'pending' anyway

    cancelled = change(client, unassigned["id"], "cancelled", "cancel-1", note="Not needed")
    assert cancelled.status_code == 200
    assert cancelled.json()["allowed_next_states"] == []
    after = change(client, unassigned["id"], "pending", "reopen-1")
    assert after.status_code == 409


def test_transitions_survive_application_restart(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'workflow.sqlite3').as_posix()}"
    app_kwargs = {"allowed_hosts": ["testserver"]}

    with TestClient(create_app(database_url, **app_kwargs)) as first_client:
        agent = create_agent(first_client)
        task = create_task(first_client, assigned_agent_id=agent)
        assert change(first_client, task["id"], "running", "persist-1").status_code == 200

    with TestClient(create_app(database_url, **app_kwargs)) as second_client:
        tasks = second_client.get("/api/v1/tasks").json()
        assert tasks[0]["state"] == "running"
        history = second_client.get(f"/api/v1/tasks/{tasks[0]['id']}/transitions").json()
        assert len(history["transitions"]) == 1

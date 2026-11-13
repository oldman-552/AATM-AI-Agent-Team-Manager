"""Execution timeline fidelity and cooperative cancellation."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import ExecutionResult, Orchestrator, OrchestratorConfig
from sqlalchemy.orm import Session


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def setup(client: TestClient) -> tuple[str, str, str]:
    project = client.post("/api/v1/projects", json={"name": "Timeline"}).json()
    agent = client.post(
        "/api/v1/agents", json={"name": "Worker", "role": "developer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Traced task", "project_id": project["id"], "assigned_agent_id": agent["id"]},
    ).json()
    return project["id"], agent["id"], task["id"]


def test_timeline_only_contains_recorded_actions(client: TestClient) -> None:
    project_id, _agent, task_id = setup(client)
    client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "started", "note": "milestone"})
    for target in ("running", "completed"):
        response = client.patch(
            f"/api/v1/tasks/{task_id}/state",
            json={"target_state": target, "idempotency_key": f"t-{target}", "note": "evidence"},
        )
        assert response.status_code == 200

    timeline = client.get(f"/api/v1/tasks/{task_id}/timeline").json()
    kinds = [entry["kind"] for entry in timeline["entries"]]
    assert "transition" in kinds and "checkpoint" in kinds
    assert timeline["total"] == len(timeline["entries"]) >= 2
    assert timeline["note"].startswith("Assembled from stored rows only")
    assert set(timeline["sources"]) <= {
        "task_transitions", "task_checkpoints", "audit_events", "review_records", "approval_requests",
    }
    # Every entry is timestamped and traceable.
    for entry in timeline["entries"]:
        assert entry["at"] and entry["reference"] and entry["source"]
    # Timestamps are non-decreasing.
    stamps = [entry["at"] for entry in timeline["entries"]]
    assert stamps == sorted(stamps)

    project_timeline = client.get(f"/api/v1/projects/{project_id}/timeline").json()
    assert project_timeline["tasks"] == 1
    assert all(entry["task_id"] == task_id for entry in project_timeline["entries"])
    assert client.get("/api/v1/projects/missing/timeline").status_code == 404
    assert client.get(f"/api/v1/tasks/{task_id}/timeline", params={"limit": 0}).status_code == 422


def test_cancel_request_is_intent_not_immediate_state_change(client: TestClient) -> None:
    _project, _agent, task_id = setup(client)
    requested = client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "No longer needed"})
    assert requested.status_code == 200, requested.text
    body = requested.json()
    assert body["state"] == "assigned"          # unchanged: an executor may be mid-flight
    assert body["cancel_reason"] == "No longer needed"
    assert body["cancel_requested_at"] is not None
    assert "next safe boundary" in body["note"]

    pending = client.get("/api/v1/cancellations").json()["pending"]
    assert [item["task_id"] for item in pending] == [task_id]

    applied = client.post(f"/api/v1/tasks/{task_id}/cancel/apply").json()
    assert applied["cancelled"] is True
    assert applied["state"] == "cancelled"
    assert client.get("/api/v1/cancellations").json()["pending"] == []


def test_cancel_requires_a_reason_and_refuses_finished_work(client: TestClient) -> None:
    _project, _agent, task_id = setup(client)
    assert client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "   "}).status_code == 422
    assert client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": ""}).status_code == 422

    client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "first"})
    duplicate = client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "second"})
    assert duplicate.status_code == 409
    assert "already requested" in duplicate.json()["detail"]

    withdrawn = client.delete(f"/api/v1/tasks/{task_id}/cancel")
    assert withdrawn.status_code == 200
    assert client.delete(f"/api/v1/tasks/{task_id}/cancel").status_code == 409

    for target in ("running", "completed"):
        client.patch(
            f"/api/v1/tasks/{task_id}/state",
            json={"target_state": target, "idempotency_key": f"c-{target}", "note": "done"},
        )
    refused = client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "too late"})
    assert refused.status_code == 409
    assert "already reached 'completed'" in refused.json()["detail"]


def test_finished_task_is_not_rewritten_by_a_pending_request(client: TestClient) -> None:
    _project, _agent, task_id = setup(client)
    client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "stop"})
    # The task finishes in the same window; applying must not rewrite the outcome.
    client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": "running", "idempotency_key": "r1", "note": "go"},
    )
    client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": "completed", "idempotency_key": "r2", "note": "done", "output": "artifact"},
    )
    result = client.post(f"/api/v1/tasks/{task_id}/cancel/apply").json()
    assert result["cancelled"] is False
    assert result["reason"] == "already_finished"
    state = [task for task in client.get("/api/v1/tasks").json() if task["id"] == task_id][0]
    assert state["state"] == "completed"


def test_orchestrator_honours_cancellations_before_claiming(client: TestClient) -> None:
    _project, _agent, task_id = setup(client)
    client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "Abort before start"})

    executed: list[str] = []

    def executor(task):
        executed.append(task.id)
        return ExecutionResult(output="ran", evidence="ok")

    with Session(client.app.state.engine) as session:
        report = Orchestrator(executor, OrchestratorConfig(owner="test")).run_once(session)
        session.commit()

    assert report.cancelled == [task_id]
    assert executed == []                       # never started
    assert report.started == []
    state = [task for task in client.get("/api/v1/tasks").json() if task["id"] == task_id][0]
    assert state["state"] == "cancelled"


def test_cancellation_requires_a_reason_through_the_workflow(client: TestClient) -> None:
    _project, _agent, task_id = setup(client)
    refused = client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": "cancelled", "idempotency_key": "k1"},
    )
    assert refused.status_code == 409
    assert "reason" in refused.json()["detail"].lower()
    accepted = client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": "cancelled", "idempotency_key": "k2", "note": "Duplicate of another task"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["task"]["state"] == "cancelled"


def test_capture_path_is_closed(client: TestClient) -> None:
    """A task that never ran must never be reported as completed."""
    _project, _agent, task_id = setup(client)
    client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "abandoned"})
    client.post("/api/v1/cancellations/apply")
    timeline = client.get(f"/api/v1/tasks/{task_id}/timeline").json()
    transitions = [entry for entry in timeline["entries"] if entry["kind"] == "transition"]
    assert any(entry["data"]["to"] == "cancelled" for entry in transitions)
    assert not any(entry["data"]["to"] == "completed" for entry in transitions)

"""Independent QA review and approval-gate tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app("sqlite://", allowed_hosts=["testserver"])
    with TestClient(app) as tc:
        yield tc


def agent(client: TestClient, name: str, role: str = "QA Engineer") -> str:
    return client.post("/api/v1/agents", json={"name": name, "role": role}).json()["id"]


def task(client: TestClient, agent_id: str, **extra) -> str:
    payload = {"title": "Reviewable task", "assigned_agent_id": agent_id}
    payload.update(extra)
    return client.post("/api/v1/tasks", json=payload).json()["id"]


def set_state(client: TestClient, task_id: str, target: str, key: str, **extra):
    payload = {"target_state": target, "idempotency_key": key, "note": extra.pop("note", "")}
    payload.update(extra)
    return client.patch(f"/api/v1/tasks/{task_id}/state", json=payload)


def completed_task(client: TestClient, worker: str) -> str:
    task_id = task(client, worker)
    assert set_state(client, task_id, "running", "r1").status_code == 200
    done = set_state(client, task_id, "completed", "c1", note="Output produced", output="Verified artifact content")
    assert done.status_code == 200
    return task_id


def review(client: TestClient, task_id: str, reviewer: str, verdict: str, key: str, **extra):
    payload = {
        "reviewer_agent_id": reviewer,
        "verdict": verdict,
        "idempotency_key": key,
    }
    payload.update(extra)
    return client.post(f"/api/v1/tasks/{task_id}/reviews", json=payload)


def test_self_review_is_rejected(client: TestClient) -> None:
    worker = agent(client, "Worker")
    task_id = completed_task(client, worker)
    response = review(
        client, task_id, worker, "approved", "self-1",
        checks=[{"check": "unit tests", "result": "passed"}],
    )
    assert response.status_code == 409
    assert "cannot be reviewed by the agent" in response.json()["detail"]


def test_approval_requires_concrete_checks_and_output(client: TestClient) -> None:
    worker = agent(client, "Worker")
    reviewer = agent(client, "Reviewer", "Code Reviewer")
    task_id = completed_task(client, worker)

    bare = review(client, task_id, reviewer, "approved", "bare-1")
    assert bare.status_code == 409
    assert "concrete check" in bare.json()["detail"]

    empty_check = review(
        client, task_id, reviewer, "approved", "empty-1",
        checks=[{"check": "", "result": "pass"}],
    )
    assert empty_check.status_code == 422  # schema rejects blank labels

    approved = review(
        client, task_id, reviewer, "approved", "ok-1",
        summary="Verified independently.",
        checks=[
            {"check": "unit tests", "result": "44 passed"},
            {"check": "no secrets in diff", "result": "pass"},
        ],
    )
    assert approved.status_code == 201
    body = approved.json()
    assert body["created"] is True
    assert body["task_state"] == "approved"
    assert len(body["review"]["checks"]) == 2

    replay = review(
        client, task_id, reviewer, "approved", "ok-1",
        summary="Verified independently.",
        checks=[{"check": "unit tests", "result": "44 passed"}],
    )
    assert replay.status_code == 201
    assert replay.json()["created"] is False

    conflicting = review(
        client, task_id, reviewer, "rework_required", "ok-1", summary="changed my mind",
    )
    assert conflicting.status_code == 409

    history = client.get(f"/api/v1/tasks/{task_id}/reviews").json()["reviews"]
    assert len(history) == 1
    assert history[0]["verdict"] == "approved"


def test_rework_requires_summary_and_drives_state(client: TestClient) -> None:
    worker = agent(client, "Worker")
    reviewer = agent(client, "Reviewer", "QA Engineer")
    task_id = completed_task(client, worker)

    missing = review(client, task_id, reviewer, "rework_required", "rw-0")
    assert missing.status_code == 409
    assert "summary" in missing.json()["detail"]

    rework = review(
        client, task_id, reviewer, "rework_required", "rw-1",
        summary="Missing error handling on empty input.",
        checks=[{"check": "edge cases", "result": "failed"}],
    )
    assert rework.status_code == 201
    assert rework.json()["task_state"] == "rework_required"
    assert client.get("/api/v1/tasks").json()[0]["retry_count"] == 1


def test_unknown_reviewer_and_unknown_task(client: TestClient) -> None:
    worker = agent(client, "Worker")
    task_id = completed_task(client, worker)
    assert review(client, task_id, "00000000-0000-0000-0000-000000000000", "approved", "x").status_code == 409
    assert review(client, "00000000-0000-0000-0000-000000000000", worker, "approved", "y").status_code == 404


def test_review_not_allowed_before_completion(client: TestClient) -> None:
    worker = agent(client, "Worker")
    reviewer = agent(client, "Reviewer")
    task_id = task(client, worker)
    response = review(
        client, task_id, reviewer, "approved", "early-1",
        checks=[{"check": "x", "result": "pass"}],
    )
    assert response.status_code == 409


def test_approval_gate_records_decision_without_executing(client: TestClient) -> None:
    created = client.post(
        "/api/v1/approvals",
        json={
            "kind": "deployment",
            "entity_type": "task",
            "summary": "Deploy the staging build after review.",
        },
    )
    assert created.status_code == 201
    approval = created.json()["approval"]
    assert approval["status"] == "pending"
    assert approval["decided_by"] is None

    pending = client.get("/api/v1/approvals", params={"status": "pending"}).json()["approvals"]
    assert [row["id"] for row in pending] == [approval["id"]]

    decided = client.patch(
        f"/api/v1/approvals/{approval['id']}",
        json={"status": "approved", "decided_by": "local-user", "note": "Reviewed the diff."},
    )
    assert decided.status_code == 200
    assert decided.json()["approval"]["status"] == "approved"
    assert "not executed" in decided.json()["note"]

    again = client.patch(
        f"/api/v1/approvals/{approval['id']}",
        json={"status": "rejected", "decided_by": "local-user"},
    )
    assert again.status_code == 409

    assert client.post(
        "/api/v1/approvals",
        json={"kind": "unknown_kind", "summary": "nope"},
    ).status_code == 422
    assert client.post(
        "/api/v1/approvals",
        json={"kind": "deployment", "entity_type": "task", "entity_id": "00000000-0000-0000-0000-000000000000", "summary": "x"},
    ).status_code == 404


def test_reviews_are_audited(client: TestClient) -> None:
    worker = agent(client, "Worker")
    reviewer = agent(client, "Reviewer")
    task_id = completed_task(client, worker)
    review(client, task_id, reviewer, "approved", "audit-1", checks=[{"check": "tests", "result": "pass"}])
    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "task.review_approved" in events
    assert events.count("task.state_changed") >= 3

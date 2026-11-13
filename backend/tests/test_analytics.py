"""Analytics must be measured from rows, not invented."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def empty_overview(client: TestClient) -> dict:
    return client.get("/api/v1/analytics").json()


def test_empty_database_reports_zeroes_not_estimates(client: TestClient) -> None:
    body = empty_overview(client)
    # A fresh database is seeded with exactly one default Manager identity.
    assert body["counts"] == {
        "projects": 0, "agents": 1, "tasks": 0, "tasks_active": 0, "tasks_terminal": 0, "checkpoints": 0,
    }
    assert body["throughput"]["total"] == 0
    assert body["cycle_time"]["samples"] == 0
    assert body["cycle_time"]["average_seconds"] is None  # never 0.0 for "no data"
    assert body["reviews"]["approval_rate"] is None
    assert body["rework"]["share"] is None
    assert len(body["activity"]["buckets"]) == 14
    # Startup seeds a Manager identity, which writes exactly one audit event.
    assert body["activity"]["total"] == 1
    assert sum(bucket["events"] for bucket in body["activity"]["buckets"]) == 1
    assert body["activity"]["buckets"][-1]["events"] == 1
    assert any("nothing is simulated" in note for note in body["notes"])


def test_counts_and_throughput_follow_real_rows(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Analytics project"}).json()
    agent = client.post(
        "/api/v1/agents", json={"name": "Engineer", "role": "developer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Measured work", "project_id": project["id"], "assigned_agent_id": agent["id"]},
    ).json()

    before = empty_overview(client)
    assert before["counts"]["tasks"] == 1
    # An assigned task is already queued, so it counts as active, not terminal.
    assert before["counts"]["tasks_active"] == 1
    assert before["counts"]["tasks_terminal"] == 0

    for target in ("running", "completed"):
        response = client.patch(
            f"/api/v1/tasks/{task['id']}/state",
            json={"target_state": target, "idempotency_key": f"k-{target}", "note": "done"},
        )
        assert response.status_code == 200, response.text

    after = empty_overview(client)
    assert after["counts"]["tasks_terminal"] == 1
    assert after["counts"]["tasks_active"] == 0
    assert after["throughput"]["total"] == 1
    assert sum(bucket["completed"] for bucket in after["throughput"]["buckets"]) == 1
    assert after["cycle_time"]["samples"] == 1
    assert after["cycle_time"]["average_seconds"] is not None
    assert after["cycle_time"]["average_seconds"] >= 0
    assert after["activity"]["total"] >= 1


def test_reviews_and_approvals_are_measured_independently(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "QA project"}).json()
    author = client.post(
        "/api/v1/agents", json={"name": "Author", "role": "developer", "project_id": project["id"]}
    ).json()
    reviewer = client.post(
        "/api/v1/agents", json={"name": "Reviewer", "role": "reviewer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Reviewed work", "project_id": project["id"], "assigned_agent_id": author["id"]},
    ).json()
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "running", "idempotency_key": "r1", "note": "go"},
    )
    client.patch(
        f"/api/v1/tasks/{task['id']}/state",
        json={"target_state": "completed", "idempotency_key": "r2", "note": "done", "output": "artifact"},
    )
    review = client.post(
        f"/api/v1/tasks/{task['id']}/reviews",
        json={
            "reviewer_agent_id": reviewer["id"],
            "verdict": "approved",
            "summary": "Verified",
            "checks": [{"check": "tests", "result": "pass"}],
            "idempotency_key": "rev-1",
        },
    )
    assert review.status_code == 201, review.text

    reviews = client.get("/api/v1/analytics/reviews").json()
    assert reviews["total"] == 1
    assert reviews["by_verdict"] == {"approved": 1}
    assert reviews["approval_rate"] == 1.0

    approvals_before = client.get("/api/v1/analytics/approvals").json()
    client.post(
        "/api/v1/approvals",
        json={"kind": "deployment", "summary": "Deploy demo", "entity_type": "project", "entity_id": project["id"]},
    )
    approvals_after = client.get("/api/v1/analytics/approvals").json()
    assert approvals_after["pending"] == approvals_before["pending"] + 1
    assert approvals_after["by_kind"]["deployment"] == 1
    assert "does not execute" in approvals_after["source"]


def test_rework_share_and_event_payloads(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Rework"}).json()
    agent = client.post(
        "/api/v1/agents", json={"name": "Dev", "role": "developer", "project_id": project["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks", json={"title": "Needs rework", "project_id": project["id"], "assigned_agent_id": agent["id"]}
    ).json()
    for target, key in (("running", "w1"), ("failed", "w2"), ("rework_required", "w3")):
        response = client.patch(
            f"/api/v1/tasks/{task['id']}/state",
            json={"target_state": target, "idempotency_key": key, "note": "evidence", "error": "broken"},
        )
        assert response.status_code == 200, response.text

    rework = client.get("/api/v1/analytics/rework").json()
    assert rework["tasks_with_rework"] == 1
    assert rework["rework_events"] >= 1
    assert rework["share"] == 1.0

    activity = client.get("/api/v1/analytics/activity", params={"days": 7}).json()
    assert len(activity["buckets"]) == 7
    assert activity["total"] >= 1
    assert client.get("/api/v1/analytics/activity", params={"days": 0}).status_code == 422
    assert client.get("/api/v1/analytics", params={"days": 400}).status_code == 422

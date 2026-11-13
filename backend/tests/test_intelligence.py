"""AI Team Intelligence Center: fair measurement, separated from assessment."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def worker(client: TestClient, name: str, role: str = "developer") -> dict:
    return client.post("/api/v1/agents", json={"name": name, "role": role}).json()


def task(client: TestClient, agent_id: str, title: str, priority: str = "normal") -> dict:
    return client.post(
        "/api/v1/tasks",
        json={"title": title, "assigned_agent_id": agent_id, "priority": priority},
    ).json()


def finish(client: TestClient, task_id: str, *, success: bool = True, prefix: str = "f") -> None:
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"target_state": "running", "idempotency_key": f"{prefix}-1", "note": "go"})
    target = "completed" if success else "failed"
    client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": target, "idempotency_key": f"{prefix}-2", "note": "outcome", "output": "artifact"},
    )


def metrics_for(report: dict, name: str) -> dict:
    return next(item for item in report["agents"] if item["name"] == name)


def test_empty_period_returns_nulls_not_zeros(client: TestClient) -> None:
    worker(client, "Idle Worker")
    report = client.get("/api/v1/intelligence").json()
    entry = metrics_for(report, "Idle Worker")
    assert entry["tasks"]["terminal"] == 0
    assert entry["success_rate"] is None
    assert entry["rework"]["rate"] is None
    assert entry["completion_time"]["median_seconds"] is None
    assert entry["sample_sufficient"] is False
    assert entry["usage"]["confirmed"] is False


def test_measured_fields_are_separate_from_assessments(client: TestClient) -> None:
    method = client.get("/api/v1/intelligence").json()["method"]
    assert method["model_generated"] is False
    assert method["assessment_kind"] == "rule_based"
    assert method["ranking"] == "none"
    assert set(method["measured_fields"]).isdisjoint(method["assessed_fields"])
    assert "success_rate" in method["measured_fields"]
    assert "assessments" in method["assessed_fields"]


def test_no_ranking_by_task_count(client: TestClient) -> None:
    """The agent with the most tasks must not automatically lead any ranking."""
    busy = worker(client, "Busy")
    quiet = worker(client, "Quiet")
    for index in range(4):
        finish(client, task(client, busy["id"], f"Busy {index}")["id"], prefix=f"b{index}")
    # Quiet has fewer tasks but a perfect record; a count ranking would put Busy first.
    report = client.get("/api/v1/intelligence").json()
    busy_metrics = metrics_for(report, "Busy")
    quiet_metrics = metrics_for(report, "Quiet")
    assert busy_metrics["tasks"]["terminal"] == 4
    assert quiet_metrics["tasks"]["terminal"] == 0
    assert quiet_metrics["success_rate"] is None
    # Count alone never produces a success assessment.
    for item in report["assessments"]:
        assert item["basis"]["metric"] != "tasks_total"


def test_complexity_is_weighted_not_counted(client: TestClient) -> None:
    heavy = worker(client, "Heavy")
    light = worker(client, "Light")
    task(client, heavy["id"], "Urgent thing", priority="urgent")
    for index in range(2):
        task(client, light["id"], f"Low thing {index}", priority="low")

    report = client.get("/api/v1/intelligence").json()
    heavy_metrics = metrics_for(report, "Heavy")
    light_metrics = metrics_for(report, "Light")

    # Two low tasks (1.0 each) outweigh one urgent task (6.0)? No: weight decides,
    # and the point is that the weighting exists and is published.
    assert heavy_metrics["complexity_points"] == 6.0
    assert light_metrics["complexity_points"] == 2.0
    assert heavy_metrics["tasks"]["total"] == 1
    assert light_metrics["tasks"]["total"] == 2
    assert report["method"]["complexity_weights"] == {"low": 1.0, "normal": 2.0, "high": 4.0, "urgent": 6.0}
    assert report["by_complexity"] == {"urgent": 1, "low": 2}


def test_success_rate_and_completion_time_are_measured(client: TestClient) -> None:
    reliable = worker(client, "Reliable")
    flaky = worker(client, "Flaky")
    for index in range(3):
        finish(client, task(client, reliable["id"], f"R{index}")["id"], prefix=f"r{index}")
    for index in range(3):
        finish(
            client,
            task(client, flaky["id"], f"F{index}")["id"],
            success=index == 0,
            prefix=f"x{index}",
        )

    report = client.get("/api/v1/intelligence").json()
    good = metrics_for(report, "Reliable")
    bad = metrics_for(report, "Flaky")
    assert good["success_rate"] == 1.0
    assert bad["success_rate"] == round(1 / 3, 3)
    assert good["tasks"]["success"] == 3
    assert bad["tasks"]["failed"] == 2
    assert good["completion_time"]["samples"] == 3
    assert good["completion_time"]["median_seconds"] is not None
    assert good["sample_sufficient"] is True

    # The gap produces a rule-based assignment assessment naming the figures.
    assignment = [item for item in report["assessments"] if item["topic"] == "assignment"]
    assert assignment, report["assessments"]
    assert "Reliable" in assignment[0]["finding"]
    assert assignment[0]["kind"] == "rule_based"
    assert assignment[0]["caveat"]


def test_thin_samples_are_flagged_rather_than_compared(client: TestClient) -> None:
    worker(client, "Newcomer")
    tiny = worker(client, "Tiny")
    finish(client, task(client, tiny["id"], "One job")["id"], prefix="t1")

    report = client.get("/api/v1/intelligence").json()
    entry = metrics_for(report, "Tiny")
    assert entry["tasks"]["terminal"] == 1
    assert entry["sample_sufficient"] is False
    method = [item for item in report["assessments"] if item["topic"] == "method"]
    assert method, "a thin sample must be called out"
    assert "noise" in method[0]["recommendation"].lower()


def test_cost_is_reported_as_unconfirmed_and_explained(client: TestClient) -> None:
    worker(client, "Costly")
    report = client.get("/api/v1/intelligence").json()
    entry = metrics_for(report, "Costly")
    assert entry["usage"]["records"] == 0
    assert entry["usage"]["confirmed"] is False
    assert "estimate" in entry["usage"]["note"].lower()
    cost = [item for item in report["assessments"] if item["topic"] == "cost"]
    assert cost, "an empty cost column must be explained, not silently zero"
    assert "never makes a paid call" in cost[0]["caveat"]


def test_role_grouping_and_period_bounds(client: TestClient) -> None:
    worker(client, "Dev One", "developer")
    worker(client, "Qa One", "qa-engineer")
    report = client.get("/api/v1/intelligence").json()
    assert "developer" in report["by_role"] and "qa-engineer" in report["by_role"]
    assert report["period"]["days"] == 90
    assert report["period"]["since"] < report["period"]["until"]
    assert client.get("/api/v1/intelligence", params={"days": 0}).status_code == 422
    assert client.get("/api/v1/intelligence", params={"days": 5000}).status_code == 422


def test_manager_is_excluded_from_worker_comparison(client: TestClient) -> None:
    report = client.get("/api/v1/intelligence").json()
    manager = next(item for item in report["agents"] if item["is_manager"])
    assert manager["name"] == "Manager"
    worker_names = {item["name"] for group in report["by_role"].values() for item in group}
    assert "Manager" not in worker_names


def test_cancelled_tasks_are_excluded_from_the_success_denominator(client: TestClient) -> None:
    """A withdrawal outside the agent's control must not be scored as a failure."""
    worker_id = worker(client, "Steady")
    good = task(client, worker_id["id"], "Completed job")
    finish(client, good["id"], prefix="s1")
    withdrawn = task(client, worker_id["id"], "Withdrawn job")
    client.post(f"/api/v1/tasks/{withdrawn['id']}/cancel", json={"reason": "Scope dropped by the operator"})
    client.patch(
        f"/api/v1/tasks/{withdrawn['id']}/state",
        json={"target_state": "cancelled", "idempotency_key": "w1", "note": "Scope dropped"},
    )

    entry = metrics_for(client.get("/api/v1/intelligence").json(), "Steady")
    assert entry["tasks"]["success"] == 1
    assert entry["tasks"]["cancelled"] == 1
    assert entry["tasks"]["terminal"] == 1          # the cancellation is not in the denominator
    assert entry["success_rate"] == 1.0
    assert "cancellations are excluded" in entry["success_rate_denominator"]


def test_a_failure_lowers_the_rate(client: TestClient) -> None:
    worker_id = worker(client, "Mixed")
    finish(client, task(client, worker_id["id"], "Good")["id"], prefix="m1")
    failed = task(client, worker_id["id"], "Bad")
    client.patch(f"/api/v1/tasks/{failed['id']}/state", json={"target_state": "running", "idempotency_key": "m2", "note": "go"})
    client.patch(
        f"/api/v1/tasks/{failed['id']}/state",
        json={"target_state": "failed", "idempotency_key": "m3", "note": "broke"},
    )
    entry = metrics_for(client.get("/api/v1/intelligence").json(), "Mixed")
    assert entry["tasks"]["terminal"] == 2
    assert entry["success_rate"] == 0.5

"""Live Agent Control Center: real state only, and honest about what is absent."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def make_worker(client: TestClient, name: str = "Worker") -> dict:
    return client.post("/api/v1/agents", json={"name": name, "role": "developer"}).json()


def test_center_reports_registered_state_and_nulls_for_absent_data(client: TestClient) -> None:
    worker = make_worker(client)
    center = client.get("/api/v1/agents/center").json()

    assert center["total"] >= 2  # seeded Manager + our worker
    entry = next(item for item in center["agents"] if item["agent_id"] == worker["id"])
    assert entry["status"] == "idle"
    assert entry["current_task"] is None
    assert entry["open_task_count"] == 0
    assert entry["latest_activity"]["event_type"] == "agent.registered"
    assert entry["usage"]["records"] == 0 and entry["usage"]["estimated_cost_usd"] == 0
    assert entry["usage"]["cost_source"] == "none"
    assert entry["execution_time"]["seconds"] is None
    assert entry["browser"]["automation_available"] is False
    assert entry["authentication"]["provider_configured"] is False
    assert entry["honesty"]["browser_automation"] is False
    assert entry["honesty"]["execution_time_kind"] == "wall_clock_not_cpu"
    assert entry["errors"] == []


def test_current_task_and_activity_come_from_rows(client: TestClient) -> None:
    worker = make_worker(client)
    project = client.post("/api/v1/projects", json={"name": "Center"}).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Visible work", "project_id": project["id"], "assigned_agent_id": worker["id"]},
    ).json()

    entry = client.get(f"/api/v1/agents/{worker['id']}/center").json()
    assert entry["current_task"]["task_id"] == task["id"]
    assert entry["current_task"]["state"] == "assigned"
    assert entry["open_task_count"] == 1
    assert entry["controls"]["reassign"] is True
    assert entry["latest_activity"]["entity_type"] == "task"
    assert entry["latest_activity"]["entity_id"] == task["id"]
    assert entry["execution_time"]["seconds"] is not None

    # Finishing the task moves it from "current" to "history".
    for target in ("running", "completed"):
        client.patch(
            f"/api/v1/tasks/{task['id']}/state",
            json={"target_state": target, "idempotency_key": f"c-{target}", "note": "evidence"},
        )
    after = client.get(f"/api/v1/agents/{worker['id']}/center").json()
    assert after["current_task"] is None
    assert [item["state"] for item in after["history"]] == ["completed"]


def test_instructions_are_recorded_but_never_claimed_delivered(client: TestClient) -> None:
    worker = make_worker(client)
    issued = client.post(
        f"/api/v1/agents/{worker['id']}/instructions",
        json={"instruction": "Prefer smaller commits and run tests before reporting."},
    )
    assert issued.status_code == 201
    assert issued.json()["delivered"] is False
    assert "Nothing executes it" in issued.json()["note"]

    listed = client.get(f"/api/v1/agents/{worker['id']}/instructions").json()
    assert len(listed["instructions"]) == 1
    assert listed["instructions"][0]["delivered"] is False
    assert "no executor is configured" in listed["delivery_note"]

    assert client.post(f"/api/v1/agents/{worker['id']}/instructions", json={"instruction": "   "}).status_code == 422


def test_instruction_task_must_belong_to_the_agent(client: TestClient) -> None:
    first = make_worker(client, "First")
    second = make_worker(client, "Second")
    task = client.post("/api/v1/tasks", json={"title": "Owned", "assigned_agent_id": first["id"]}).json()
    mismatch = client.post(
        f"/api/v1/agents/{second['id']}/instructions",
        json={"instruction": "steer", "task_id": task["id"]},
    )
    assert mismatch.status_code == 409
    missing = client.post(
        f"/api/v1/agents/{first['id']}/instructions",
        json={"instruction": "steer", "task_id": "does-not-exist"},
    )
    assert missing.status_code == 404


@pytest.mark.parametrize("blocked_status", ["paused", "disabled"])
def test_reassign_refuses_unavailable_targets(client: TestClient, blocked_status: str) -> None:
    first = make_worker(client, "Holder")
    target = make_worker(client, "Target")
    task = client.post("/api/v1/tasks", json={"title": "Movable", "assigned_agent_id": first["id"]}).json()

    if blocked_status == "paused":
        client.patch(f"/api/v1/agents/{target['id']}/state", json={"target_state": "active"})
        client.patch(f"/api/v1/agents/{target['id']}/state", json={"target_state": "paused"})
    else:
        client.patch(f"/api/v1/agents/{target['id']}/state", json={"target_state": "disabled"})

    refused = client.post(
        f"/api/v1/agents/{first['id']}/reassign",
        json={"task_id": task["id"], "to_agent_id": target["id"], "note": "rebalance"},
    )
    assert refused.status_code == 409
    assert blocked_status in refused.json()["detail"].lower() or "cannot take work" in refused.json()["detail"]


def test_reassign_moves_work_and_is_audited(client: TestClient) -> None:
    first = make_worker(client, "From")
    second = make_worker(client, "To")
    task = client.post("/api/v1/tasks", json={"title": "Handover", "assigned_agent_id": first["id"]}).json()

    moved = client.post(
        f"/api/v1/agents/{first['id']}/reassign",
        json={"task_id": task["id"], "to_agent_id": second["id"], "note": "second has capacity"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["to_agent_id"] == second["id"]

    tasks = {item["id"]: item for item in client.get("/api/v1/tasks").json()}
    assert tasks[task["id"]]["assigned_agent_id"] == second["id"]
    timeline = client.get(f"/api/v1/tasks/{task['id']}/timeline").json()
    assert any(entry["data"].get("event_type") == "task.reassigned" for entry in timeline["entries"])

    # The old holder no longer owns it.
    assert client.post(
        f"/api/v1/agents/{first['id']}/reassign",
        json={"task_id": task["id"], "to_agent_id": None, "note": "again"},
    ).status_code == 409


def test_reassign_refuses_manager_and_finished_work(client: TestClient) -> None:
    worker = make_worker(client)
    manager = next(item for item in client.get("/api/v1/agents").json() if item["is_manager"])
    task = client.post("/api/v1/tasks", json={"title": "Guarded", "assigned_agent_id": worker["id"]}).json()

    to_manager = client.post(
        f"/api/v1/agents/{worker['id']}/reassign",
        json={"task_id": task["id"], "to_agent_id": manager["id"], "note": "escalate"},
    )
    assert to_manager.status_code == 409
    assert "Manager" in to_manager.json()["detail"]

    for target in ("running", "completed"):
        client.patch(
            f"/api/v1/tasks/{task['id']}/state",
            json={"target_state": target, "idempotency_key": f"f-{target}", "note": "evidence"},
        )
    finished = client.post(
        f"/api/v1/agents/{worker['id']}/reassign",
        json={"task_id": task["id"], "to_agent_id": None, "note": "too late"},
    )
    assert finished.status_code == 409
    assert "finished work" in finished.json()["detail"]


def test_manager_has_no_pause_or_stop_control(client: TestClient) -> None:
    manager = next(item for item in client.get("/api/v1/agents").json() if item["is_manager"])
    entry = client.get(f"/api/v1/agents/{manager['id']}/center").json()
    assert entry["controls"]["pause"] is False
    assert entry["controls"]["stop"] is False
    assert entry["controls"]["instructions"] is True
    assert entry["is_manager"] is True

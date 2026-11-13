"""Deterministic manager planning: proposals, ordering, application, staleness."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def setup_project(client: TestClient, agent_names=("Alice", "Bob")) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Planning"}).json()
    agents = [
        client.post("/api/v1/agents", json={"name": name, "role": "developer", "project_id": project["id"]}).json()
        for name in agent_names
    ]
    return {"project": project, "agents": agents}


def make_task(client: TestClient, project_id: str, title: str, **extra) -> dict:
    payload = {"title": title, "project_id": project_id, **extra}
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_unassigned_tasks_get_least_loaded_proposals(client: TestClient) -> None:
    ctx = setup_project(client)
    first = make_task(client, ctx["project"]["id"], "First job")
    second = make_task(client, ctx["project"]["id"], "Second job")
    plan = client.get("/api/v1/planning/proposals", params={"project_id": ctx["project"]["id"]}).json()
    assert plan["applies_automatically"] is False
    assert "no model was called" in plan["planner"]
    assert len(plan["proposals"]) == 2
    suggested = {proposal["task_id"]: proposal["suggested_agent_id"] for proposal in plan["proposals"]}
    # Load balancing must not put both tasks on the same agent.
    assert suggested[first["id"]] != suggested[second["id"]]
    assert {suggested[first["id"]], suggested[second["id"]]} == {agent["id"] for agent in ctx["agents"]}
    assert all(proposal["reason_code"] == "assign_least_loaded" for proposal in plan["proposals"])
    assert plan["plan_id"]


def test_dependency_order_and_cycle_detection(client: TestClient) -> None:
    ctx = setup_project(client)
    project_id = ctx["project"]["id"]
    blocker = make_task(client, project_id, "Blocker", priority="urgent")
    dependent = make_task(client, project_id, "Dependent", dependencies=[blocker["id"]])
    plan = client.get("/api/v1/planning/proposals", params={"project_id": project_id}).json()
    order = plan["order"]
    assert order.index(blocker["id"]) < order.index(dependent["id"])
    # A blocked task is not proposed for assignment yet.
    assert dependent["id"] not in {proposal["task_id"] for proposal in plan["proposals"]}

    # A real cycle cannot be created through the API (dependencies must already
    # exist), so build one directly in the database and confirm it is reported
    # instead of silently ignored or "fixed".
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models import Task as TaskModel

    cyclic_a = make_task(client, project_id, "Cycle A", dependencies=[dependent["id"]])
    with Session(client.app.state.engine) as session:
        session.execute(update(TaskModel).where(TaskModel.id == blocker["id"]).values(dependencies=[cyclic_a["id"]]))
        session.commit()

    plan = client.get("/api/v1/planning/proposals", params={"project_id": project_id}).json()
    assert set(plan["dependency_cycles"]) >= {blocker["id"], cyclic_a["id"]}
    assert any(finding["code"] == "dependency_cycle" for finding in plan["findings"])


def test_assigning_reduces_duplicate_proposals(client: TestClient) -> None:
    ctx = setup_project(client)
    agent = ctx["agents"][0]
    task = make_task(client, ctx["project"]["id"], "Preassigned", assigned_agent_id=agent["id"])
    plan = client.get("/api/v1/planning/proposals", params={"project_id": ctx["project"]["id"]}).json()
    assert task["id"] not in {proposal["task_id"] for proposal in plan["proposals"]}


def test_apply_writes_assignments_and_audits(client: TestClient) -> None:
    ctx = setup_project(client)
    make_task(client, ctx["project"]["id"], "Apply me")
    plan = client.get("/api/v1/planning/proposals", params={"project_id": ctx["project"]["id"]}).json()
    applied = client.post("/api/v1/planning/apply", json={"plan": plan, "actor": "manager"})
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert len(body["applied"]) == 1
    assert body["skipped"] == []

    tasks = client.get("/api/v1/tasks").json()
    assigned = [task for task in tasks if task["title"] == "Apply me"][0]
    assert assigned["assigned_agent_id"] == body["applied"][0]["agent_id"]
    assert assigned["state"] == "assigned"

    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "task.planned_assignment" in events
    assert "manager.plan_applied" in events


def test_stale_plan_is_skipped_not_forced(client: TestClient) -> None:
    ctx = setup_project(client)
    task = make_task(client, ctx["project"]["id"], "Racing task")
    plan = client.get("/api/v1/planning/proposals", params={"project_id": ctx["project"]["id"]}).json()
    # Someone assigns it manually before the plan is applied.
    client.patch(f"/api/v1/tasks/{task['id']}/assignment", json={"assigned_agent_id": ctx["agents"][1]["id"]})
    result = client.post("/api/v1/planning/apply", json={"plan": plan}).json()
    assert result["applied"] == []
    assert result["skipped"][0]["reason"] == "already_assigned"

    tasks = client.get("/api/v1/tasks").json()
    assert [row for row in tasks if row["id"] == task["id"]][0]["assigned_agent_id"] == ctx["agents"][1]["id"]


def test_apply_requires_a_real_plan_and_unknown_projects_404(client: TestClient) -> None:
    ctx = setup_project(client)
    assert client.post("/api/v1/planning/apply", json={"plan": {}}).status_code == 422
    assert client.get("/api/v1/planning/proposals", params={"project_id": "missing"}).status_code == 404
    forged = {"plan_id": "deadbeef", "proposals": [{"task_id": "missing", "suggested_agent_id": ctx["agents"][0]["id"]}]}
    result = client.post("/api/v1/planning/apply", json={"plan": forged}).json()
    assert result["skipped"][0]["reason"] == "missing_task"


def test_targeting_a_wrong_project_is_rejected(client: TestClient) -> None:
    ctx = setup_project(client)
    task = make_task(client, ctx["project"]["id"], "Scoped")
    plan = client.get("/api/v1/planning/proposals", params={"project_id": ctx["project"]["id"]}).json()
    plan["project_id"] = "does-not-exist"
    assert client.post("/api/v1/planning/apply", json={"plan": plan}).status_code == 404
    assert [row for row in client.get("/api/v1/tasks").json() if row["id"] == task["id"]][0]["assigned_agent_id"] is None

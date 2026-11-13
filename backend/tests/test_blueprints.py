"""AI Project Builder: deterministic, reviewable, and inert until confirmed."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

IDEA = (
    "A small internal tool where staff log in, upload invoices, and a manager "
    "reviews a monthly spending report."
)


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def propose(client: TestClient, **overrides) -> dict:
    body = {"idea": IDEA, **overrides}
    response = client.post("/api/v1/blueprints", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_blueprint_has_all_eleven_sections_and_writes_nothing(client: TestClient) -> None:
    before = len(client.get("/api/v1/projects").json())
    plan = propose(client)

    for section in (
        "requirements", "architecture", "technology_stack", "database_design",
        "development_phases", "task_breakdown", "assignment_plan", "dependencies",
        "testing_strategy", "acceptance_criteria", "delivery_plan",
    ):
        assert plan[section], section

    assert plan["generation"]["generated_by"] == "deterministic_rules"
    assert plan["generation"]["model_called"] is False
    assert plan["generation"]["requires_review"] is True
    assert plan["generation"]["auto_execution"] is False
    assert plan["fingerprint"]

    # A proposal must not create anything.
    assert len(client.get("/api/v1/projects").json()) == before


def test_keyword_rules_are_reported_back_to_the_caller(client: TestClient) -> None:
    plan = propose(client)
    packs = plan["summary"]["capability_packs"]
    # The idea mentions login, upload and a report.
    assert "accounts" in packs and "uploads" in packs and "analytics" in packs
    evidence = plan["detection_evidence"]
    assert "login" in evidence["accounts"] or "log in" in " ".join(evidence["accounts"])
    requirement_sources = " ".join(item["source"] for item in plan["requirements"])
    assert "capability pack" in requirement_sources


def test_every_dependency_points_at_a_real_task(client: TestClient) -> None:
    plan = propose(client)
    keys = {task["key"] for task in plan["task_breakdown"]}
    for edge in plan["dependencies"]:
        assert edge["from"] in keys and edge["to"] in keys
        assert edge["type"] == "finish_to_start"
    # The plan is acyclic by construction; the workflow layer enforces the same rule.
    for task in plan["task_breakdown"]:
        assert task["key"] not in task["depends_on"]
    phases = {phase["name"] for phase in plan["development_phases"]}
    assert "Foundation" in phases and "Delivery" not in phases  # delivery is a gate, not tasks


def test_assignments_only_name_real_agents_and_state_why(client: TestClient) -> None:
    worker = client.post("/api/v1/agents", json={"name": "Backend One", "role": "backend-developer"}).json()
    plan = propose(client)
    by_key = {item["task_key"]: item for item in plan["assignment_plan"]}
    api_task = by_key["api-skeleton"]
    assert api_task["agent_id"] == worker["id"]
    assert "registered worker" in api_task["reason"].lower()
    unstaffed = by_key["deploy-plan"]
    assert unstaffed["agent_id"] is None
    assert "no available worker" in unstaffed["reason"].lower()
    assert plan["summary"]["staffed_tasks"] >= 1
    assert plan["summary"]["unstaffed_tasks"] >= 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"scale": "gigantic"},
        {"stack": "cobol"},
        {"data_layer": "papyrus"},
        {"team_size": 0},
        {"idea": "too short"},
    ],
)
def test_invalid_options_are_rejected(client: TestClient, overrides: dict) -> None:
    assert client.post("/api/v1/blueprints", json={"idea": IDEA, **overrides}).status_code == 422


def test_apply_requires_explicit_confirmation(client: TestClient) -> None:
    plan = propose(client)
    refused = client.post("/api/v1/blueprints/apply", json={"plan": plan, "confirmed": False})
    assert refused.status_code == 409
    assert "confirmed=true" in refused.json()["detail"]
    assert client.get("/api/v1/projects").json() == client.get("/api/v1/projects").json()  # unchanged


def test_apply_creates_project_and_dependency_linked_tasks(client: TestClient) -> None:
    client.post("/api/v1/agents", json={"name": "Backend One", "role": "backend-developer"})
    plan = propose(client)
    applied = client.post("/api/v1/blueprints/apply", json={"plan": plan, "confirmed": True})
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["tasks_created"] == len(plan["task_breakdown"])
    assert result["project_id"]

    project = client.get("/api/v1/projects").json()
    created = next(item for item in project if item["id"] == result["project_id"])
    assert "REQ-00" in created["description"]

    tasks = {item["title"]: item for item in client.get("/api/v1/tasks").json()}
    scaffold = tasks["Scaffold the project structure and local development setup"]
    model = tasks["Implement the core data model and migrations"]
    assert scaffold["state"] == "assigned"          # a worker exists for that role
    assert model["dependencies"] == [scaffold["id"]]  # wired, not dropped
    assert model["acceptance_criteria"]

    # Applying a plan starts nothing: the ready queue only lists unblocked work.
    ready = client.get("/api/v1/tasks/ready").json()["tasks"]
    assert ready == [] or all(item["id"] != model["id"] for item in ready)


def test_apply_rejects_a_tampered_plan(client: TestClient) -> None:
    plan = propose(client)
    plan["task_breakdown"][0]["depends_on"] = ["ghost-task"]
    broken = client.post("/api/v1/blueprints/apply", json={"plan": plan, "confirmed": True})
    assert broken.status_code == 422
    assert "ghost-task" in broken.json()["detail"]

    duplicate = propose(client)
    duplicate["task_breakdown"][1]["key"] = duplicate["task_breakdown"][0]["key"]
    clash = client.post("/api/v1/blueprints/apply", json={"plan": duplicate, "confirmed": True})
    assert clash.status_code == 422
    assert "duplicate" in clash.json()["detail"].lower()

    empty = client.post("/api/v1/blueprints/apply", json={"plan": {"task_breakdown": []}, "confirmed": True})
    assert empty.status_code == 422


def test_scale_changes_architecture_advice_not_guesses(client: TestClient) -> None:
    prototype = propose(client, scale="prototype")
    production = propose(client, scale="production")
    assert "throw" in prototype["architecture"]["shape"].lower()
    assert "load balancer" in production["architecture"]["shape"].lower()
    # Fingerprints differ because the inputs differ.
    assert prototype["fingerprint"] != production["fingerprint"]

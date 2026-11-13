"""Pull-request plans: validation, gating, and the honest refusal to execute."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def make_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "GitHub project"}).json()["id"]


def plan_payload(**overrides) -> dict:
    payload = {
        "owner": "example-org",
        "repo": "aatm-demo",
        "base_branch": "main",
        "head_branch": "feature/login",
        "title": "Add login flow",
        "body": "Implements the login flow.",
    }
    payload.update(overrides)
    return payload


def test_plan_is_recorded_with_a_gating_approval(client: TestClient) -> None:
    project_id = make_project(client)
    response = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    plan = body["plan"]
    assert plan["status"] == "awaiting_approval"
    assert plan["executed"] is False
    assert plan["execution_available"] is False
    assert plan["repository"] == "example-org/aatm-demo"
    assert plan["approval_id"] == body["approval"]["id"]

    approvals = client.get("/api/v1/approvals").json()["approvals"]
    matching = [item for item in approvals if item["id"] == plan["approval_id"]]
    assert matching and matching[0]["kind"] == "pull_request"


def test_plan_commands_are_inert_text_and_never_run(client: TestClient) -> None:
    project_id = make_project(client)
    plan = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload()).json()["plan"]
    commands = plan["commands"]
    assert any(command.startswith("git push") for command in commands)
    assert any("gh pr create" in command for command in commands)
    # The head branch is quoted into the plan but no branch is created anywhere.
    assert any("feature/login" in command for command in commands)


def test_execution_is_refused_with_a_reason(client: TestClient) -> None:
    project_id = make_project(client)
    plan = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload()).json()["plan"]
    response = client.post(f"/api/v1/projects/{project_id}/pull-requests/{plan['id']}/execute")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["executed"] is False
    assert detail["execution_available"] is False
    assert "not implemented" in detail["reason"]
    # Still not executed after the refusal.
    listed = client.get(f"/api/v1/projects/{project_id}/pull-requests").json()["plans"][0]
    assert listed["executed"] is False


def test_decision_mirrors_the_approval_without_executing(client: TestClient) -> None:
    project_id = make_project(client)
    plan = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload()).json()["plan"]
    approved = client.post(
        f"/api/v1/projects/{project_id}/pull-requests/{plan['id']}/decision",
        json={"status": "approved", "decided_by": "reviewer", "note": "Looks safe"},
    )
    assert approved.status_code == 200
    assert approved.json()["plan"]["status"] == "approved_not_executed"
    assert approved.json()["plan"]["executed"] is False
    second = client.post(
        f"/api/v1/projects/{project_id}/pull-requests/{plan['id']}/decision",
        json={"status": "approved", "decided_by": "reviewer"},
    )
    assert second.status_code == 409

    rejected_plan = client.post(
        f"/api/v1/projects/{project_id}/pull-requests",
        json=plan_payload(head_branch="feature/other", title="Other"),
    ).json()["plan"]
    rejected = client.post(
        f"/api/v1/projects/{project_id}/pull-requests/{rejected_plan['id']}/decision",
        json={"status": "rejected", "decided_by": "reviewer", "note": "Not yet"},
    )
    assert rejected.json()["plan"]["status"] == "rejected"


def test_validation_rejects_unsafe_or_ambiguous_input(client: TestClient) -> None:
    project_id = make_project(client)
    cases = {
        "owner": {"owner": "-bad-"},
        "repo": {"repo": "../etc"},
        "empty repo": {"repo": ""},
        "dot repo": {"repo": ".."},
        "base": {"base_branch": "main..evil"},
        "head": {"head_branch": "/leading-slash"},
        "same branch": {"head_branch": "main", "base_branch": "main"},
        "title": {"title": "   "},
        "long body": {"body": "x" * 20_001},
    }
    for label, overrides in cases.items():
        response = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload(**overrides))
        assert response.status_code == 422, (label, response.text)
    assert client.get("/api/v1/projects/missing/pull-requests").status_code == 404


def test_duplicate_open_plans_are_rejected(client: TestClient) -> None:
    project_id = make_project(client)
    first = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload())
    assert first.status_code == 201
    duplicate = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload())
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.json()["detail"]

    # After a rejection the same branch may be planned again.
    plan_id = first.json()["plan"]["id"]
    client.post(
        f"/api/v1/projects/{project_id}/pull-requests/{plan_id}/decision",
        json={"status": "rejected", "decided_by": "reviewer"},
    )
    again = client.post(f"/api/v1/projects/{project_id}/pull-requests", json=plan_payload())
    assert again.status_code == 201


def test_plans_are_isolated_per_project_and_audited(client: TestClient) -> None:
    first = make_project(client)
    second = make_project(client)
    plan = client.post(f"/api/v1/projects/{first}/pull-requests", json=plan_payload()).json()["plan"]
    assert client.get(f"/api/v1/projects/{second}/pull-requests").json()["plans"] == []
    assert client.post(f"/api/v1/projects/{second}/pull-requests/{plan['id']}/execute").status_code == 404
    events = client.get("/api/v1/events").json()
    summaries = [event["summary"] for event in events]
    assert any("recorded (no network call)" in summary for summary in summaries)

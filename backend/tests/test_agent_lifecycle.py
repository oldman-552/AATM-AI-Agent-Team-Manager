"""Agent lifecycle gates and deny-by-default permission scopes."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def make_agent(client: TestClient, **extra) -> dict:
    payload = {"name": extra.pop("name", "Worker"), "role": "developer", **extra}
    response = client.post("/api/v1/agents", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_task(client: TestClient, agent_id: str | None = None) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Lifecycle"}).json()
    payload = {"title": "Gated work", "project_id": project["id"]}
    if agent_id:
        payload["assigned_agent_id"] = agent_id
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_lifecycle_transitions_are_validated(client: TestClient) -> None:
    agent = make_agent(client)
    assert agent["status"] == "idle"
    assert client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "paused"}).status_code == 409

    active = client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "active"})
    assert active.json()["status"] == "active"
    paused = client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "paused", "note": "break"})
    assert paused.json()["status"] == "paused"

    disabled = client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "disabled"})
    assert disabled.json()["status"] == "disabled"
    # A disabled agent is a deliberate state; it cannot silently come back.
    assert client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "active"}).status_code == 409
    assert client.patch("/api/v1/agents/missing/state", json={"target_state": "active"}).status_code == 404
    assert client.patch(f"/api/v1/agents/{agent['id']}/state", json={"target_state": "exploded"}).status_code == 409


def pause(client: TestClient, agent_id: str) -> None:
    """idle → active → paused; idle cannot jump straight to paused."""
    assert client.patch(f"/api/v1/agents/{agent_id}/state", json={"target_state": "active"}).status_code == 200
    assert client.patch(f"/api/v1/agents/{agent_id}/state", json={"target_state": "paused"}).status_code == 200


def test_paused_and_disabled_agents_cannot_take_work(client: TestClient) -> None:
    agent = make_agent(client)
    task = make_task(client, agent["id"])
    pause(client, agent["id"])

    other = make_agent(client, name="Other")
    reassigned = client.patch(f"/api/v1/tasks/{task['id']}/assignment", json={"assigned_agent_id": other["id"]})
    assert reassigned.status_code == 200  # an idle agent is fine
    paused = client.patch(f"/api/v1/tasks/{task['id']}/assignment", json={"assigned_agent_id": agent["id"]})
    assert paused.status_code == 409
    assert "agent_paused" in paused.json()["detail"]
    # Existing work is not silently dropped when an agent pauses; it is reported.
    client.patch(f"/api/v1/tasks/{task['id']}/assignment", json={"assigned_agent_id": other["id"]})

    refused = client.post(
        "/api/v1/tasks",
        json={"title": "New work", "assigned_agent_id": agent["id"]},
    )
    assert refused.status_code == 409
    assert "agent_paused" in refused.json()["detail"]


def test_manager_cannot_be_disabled_or_assigned(client: TestClient) -> None:
    assert client.patch("/api/v1/agents/manager/state", json={"target_state": "disabled"}).status_code == 409
    manager_task = client.post("/api/v1/tasks", json={"title": "Manager work", "assigned_agent_id": "manager"})
    assert manager_task.status_code == 409
    assert "manager_is_not_a_worker" in manager_task.json()["detail"]


def test_permissions_are_deny_by_default_and_validated(client: TestClient) -> None:
    agent = make_agent(client)
    assert agent["permissions"] == []

    scopes = client.get("/api/v1/agents/scopes").json()
    assert scopes["default"] == "deny"
    assert "task:write" in scopes["scopes"]

    assert client.patch(
        f"/api/v1/agents/{agent['id']}/permissions", json={"permissions": ["root:everything"]}
    ).status_code == 422
    assert client.patch(
        f"/api/v1/agents/{agent['id']}/permissions", json={"permissions": ["task:assign"]}
    ).status_code == 200  # stored, but reserved: enforcement is separate

    updated = client.patch(
        f"/api/v1/agents/{agent['id']}/permissions",
        json={"permissions": ["task:read", "task:write", "task:read"]},
    ).json()
    assert updated["permissions"] == ["task:read", "task:write"]  # de-duplicated and sorted

    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "agent.permissions_changed" in events


def test_manager_only_scope_is_enforced(client: TestClient) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.agents import AgentError, require_scope
    from app.models import Agent as AgentModel

    agent = make_agent(client, permissions=["task:assign"])
    with Session(client.app.state.engine) as session:
        row = session.scalar(select(AgentModel).where(AgentModel.id == agent["id"]))
        with pytest.raises(AgentError, match="reserved for the Manager"):
            require_scope(row, "task:assign")
        row.permissions = ["task:write"]
        with pytest.raises(AgentError, match="does not hold"):
            require_scope(row, "task:read")
        require_scope(row, "task:write")  # granted scope passes


def test_blocked_agents_reports_open_work(client: TestClient) -> None:
    agent = make_agent(client)
    make_task(client, agent["id"])
    pause(client, agent["id"])
    # The agent paused while holding work: exactly the case an operator must see.
    blocked = client.get("/api/v1/agents/blocked").json()["agents"]
    assert blocked and blocked[0]["agent_id"] == agent["id"]
    assert blocked[0]["open_tasks"] == 1
    assert blocked[0]["reason"] == "agent_paused"

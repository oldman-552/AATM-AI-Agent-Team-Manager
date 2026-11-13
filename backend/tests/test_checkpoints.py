"""Durable checkpoints, resume guidance and secret rejection."""

import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def make_task(client: TestClient) -> str:
    project = client.post("/api/v1/projects", json={"name": "Checkpoint project"}).json()
    agent = client.post("/api/v1/agents", json={"name": "Worker", "role": "developer", "project_id": project["id"]}).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Long job", "project_id": project["id"], "assigned_agent_id": agent["id"]},
    ).json()
    return task["id"]


def test_checkpoint_sequences_are_monotonic_and_append_only(client: TestClient) -> None:
    task_id = make_task(client)
    first = client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "step 1", "state": {"done": 1}})
    second = client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "step 2", "state": {"done": 2}})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["checkpoint"]["sequence"] == 1
    assert second.json()["checkpoint"]["sequence"] == 2

    listing = client.get(f"/api/v1/tasks/{task_id}/checkpoints").json()["checkpoints"]
    assert [item["label"] for item in listing] == ["step 1", "step 2"]
    assert [item["sequence"] for item in listing] == [1, 2]


def test_checkpoints_reject_secret_shaped_values(client: TestClient) -> None:
    task_id = make_task(client)
    for payload in (
        {"label": "leak", "state": {"api_key": "anything"}},
        {"label": "leak", "state": {"note": "sk-abcdefghijklmnop1234"}},
        {"label": "leak", "note": "Bearer abcdefghijklmnopqrstuvwx"},
        {"label": "leak", "state": {"token": "x"}},
    ):
        response = client.post(f"/api/v1/tasks/{task_id}/checkpoints", json=payload)
        assert response.status_code == 422, payload
        assert "credential" in response.json()["detail"].lower() or "secret" in response.json()["detail"].lower()
    assert client.get(f"/api/v1/tasks/{task_id}/checkpoints").json()["checkpoints"] == []


def test_checkpoint_validation_errors(client: TestClient) -> None:
    task_id = make_task(client)
    assert client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": ""}).status_code == 422
    assert client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "x" * 121}).status_code == 422
    assert client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "ok with symbols !!"}).status_code == 422
    assert client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "ok", "note": "n" * 501}).status_code == 422
    assert client.post("/api/v1/tasks/missing/checkpoints", json={"label": "ok"}).status_code == 404
    assert client.get("/api/v1/tasks/missing/checkpoints").status_code == 404
    assert client.post(
        f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "ok", "state": {"blob": "x" * 9000}}
    ).status_code == 422


def test_resume_plan_is_guidance_not_automatic_resumption(client: TestClient) -> None:
    task_id = make_task(client)
    plan = client.get(f"/api/v1/tasks/{task_id}/resume-plan").json()
    assert plan["resumed_automatically"] is False
    assert plan["checkpoint_count"] == 0
    assert any("No checkpoints" in action for action in plan["next_actions"])
    assert any("queued" in action or "pending" in action for action in plan["next_actions"])

    client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": "after setup", "state": {"step": 3}})
    plan = client.get(f"/api/v1/tasks/{task_id}/resume-plan").json()
    assert plan["checkpoint_count"] == 1
    assert plan["latest_checkpoint"]["label"] == "after setup"
    assert any("after setup" in action for action in plan["next_actions"])


def test_resume_plan_reports_expired_lease(client: TestClient) -> None:
    task_id = make_task(client)
    started = client.patch(
        f"/api/v1/tasks/{task_id}/state",
        json={"target_state": "running", "idempotency_key": "start-1", "note": "handed to a worker"},
    )
    assert started.status_code == 200, started.text

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import Task as TaskModel

    with Session(client.app.state.engine) as session:
        task = session.scalar(select(TaskModel).where(TaskModel.id == task_id))
        task.lease_owner = "stale-worker"
        task.lease_expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        session.commit()

    plan = client.get(f"/api/v1/tasks/{task_id}/resume-plan").json()
    assert any("lease has expired" in action for action in plan["next_actions"])
    assert plan["lease_expires_at"] is not None

    # A live lease is treated differently from an expired one.
    with Session(client.app.state.engine) as session:
        task = session.scalar(select(TaskModel).where(TaskModel.id == task_id))
        task.lease_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        session.commit()
    live = client.get(f"/api/v1/tasks/{task_id}/resume-plan").json()
    assert any("live lease" in action for action in live["next_actions"])


def test_prune_keeps_the_newest_checkpoints(client: TestClient) -> None:
    task_id = make_task(client)
    for index in range(5):
        client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": f"step {index}"})
    pruned = client.delete(f"/api/v1/tasks/{task_id}/checkpoints", params={"keep": 2}).json()
    assert pruned["removed"] == 3
    assert pruned["latest"]["label"] == "step 4"
    remaining = client.get(f"/api/v1/tasks/{task_id}/checkpoints").json()["checkpoints"]
    assert [item["label"] for item in remaining] == ["step 3", "step 4"]
    assert client.delete(f"/api/v1/tasks/{task_id}/checkpoints", params={"keep": 0}).status_code == 422

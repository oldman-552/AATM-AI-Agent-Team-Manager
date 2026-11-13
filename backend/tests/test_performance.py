"""Performance guardrails.

These are not micro-benchmarks; they are sanity ceilings that catch accidental
quadratic behaviour or an unbounded query. The threshold is deliberately loose
so the suite stays reliable on a loaded machine: a failure means something is
wrong by orders of magnitude, not that a machine was briefly busy.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

N_TASKS = 60


@pytest.fixture(scope="module")
def loaded_client(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("perf")
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as client:
        project = client.post("/api/v1/projects", json={"name": "Perf"}).json()
        agents = [
            client.post("/api/v1/agents", json={"name": f"W{i}", "role": "developer"}).json()
            for i in range(4)
        ]
        task_ids = []
        for index in range(N_TASKS):
            task = client.post(
                "/api/v1/tasks",
                json={
                    "title": f"Task {index}",
                    "project_id": project["id"],
                    "assigned_agent_id": agents[index % 4]["id"],
                },
            ).json()
            task_ids.append(task["id"])
        # Give the timeline something substantial to project.
        for index, task_id in enumerate(task_ids):
            client.post(f"/api/v1/tasks/{task_id}/checkpoints", json={"label": f"cp-{index}"})
            if index % 3 == 0:
                client.patch(
                    f"/api/v1/tasks/{task_id}/state",
                    json={"target_state": "running", "idempotency_key": f"perf-{index}", "note": "start"},
                )
        yield client, project["id"], task_ids


def timed(callable_, repeat: int = 5) -> float:
    """Median wall time, so one unlucky sample does not fail the suite."""
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        callable_()
        samples.append(time.perf_counter() - start)
    samples.sort()
    return samples[len(samples) // 2]


def test_list_endpoints_stay_fast_with_a_populated_database(loaded_client) -> None:
    client, _project_id, _task_ids = loaded_client
    for path in ("/api/v1/tasks", "/api/v1/agents", "/api/v1/projects", "/api/v1/agents/center"):
        elapsed = timed(lambda p=path: client.get(p))
        assert elapsed < 1.0, f"{path} took {elapsed:.3f}s"


def test_dashboard_aggregation_scales(loaded_client) -> None:
    client, _project_id, _task_ids = loaded_client
    elapsed = timed(lambda: client.get("/api/v1/dashboard"))
    assert elapsed < 1.0, f"dashboard took {elapsed:.3f}s"


def test_timeline_is_bounded_by_its_limit(loaded_client) -> None:
    client, _project_id, task_ids = loaded_client
    small = client.get(f"/api/v1/tasks/{task_ids[0]}/timeline", params={"limit": 2}).json()
    assert len(small["entries"]) <= 2
    assert small["truncated"] is True

    elapsed = timed(lambda: client.get(f"/api/v1/projects/{_project_id}/timeline", params={"limit": 100}))
    assert elapsed < 1.5, f"project timeline took {elapsed:.3f}s"
    full = client.get(f"/api/v1/projects/{_project_id}/timeline", params={"limit": 100}).json()
    assert len(full["entries"]) <= 100


def test_blueprint_generation_does_not_scale_with_task_count(loaded_client) -> None:
    client, _project_id, _task_ids = loaded_client
    body = {"idea": "A booking tool where staff sign in and upload documents for review.", "scale": "mvp"}
    elapsed = timed(lambda: client.post("/api/v1/blueprints", json=body), repeat=3)
    assert elapsed < 1.5, f"blueprint took {elapsed:.3f}s"


def test_pagination_limit_is_enforced(loaded_client) -> None:
    client, _project_id, _task_ids = loaded_client
    assert client.get("/api/v1/tasks", params={"limit": 1000}).status_code == 422
    assert client.get("/api/v1/tasks", params={"limit": 5}).status_code == 200
    assert len(client.get("/api/v1/tasks", params={"limit": 5}).json()) == 5

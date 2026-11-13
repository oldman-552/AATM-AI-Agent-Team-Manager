"""Project-isolated memory: isolation, versioning, retrieval and rollback."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app("sqlite://", allowed_hosts=["testserver"])) as tc:
        yield tc


def project(client: TestClient, name: str = "Memory Project") -> str:
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


def write(client: TestClient, **payload):
    body = {"title": "Conventions", "content": "Use SQLite locally."}
    body.update(payload)
    return client.post("/api/v1/memory", json=body)


def test_project_memory_is_isolated_between_projects(client: TestClient) -> None:
    alpha = project(client, "Alpha")
    beta = project(client, "Beta")
    created = write(client, project_id=alpha, content="Alpha uses PostgreSQL.")
    assert created.status_code == 201
    assert created.json()["created"] is True

    alpha_list = client.get("/api/v1/memory", params={"project_id": alpha}).json()["entries"]
    beta_list = client.get("/api/v1/memory", params={"project_id": beta}).json()["entries"]
    assert len(alpha_list) == 1
    assert beta_list == []

    entry_id = created.json()["entry"]["id"]
    # Cross-project direct access must not leak.
    assert client.get(f"/api/v1/memory/{entry_id}", params={"project_id": beta}).status_code == 404
    assert client.delete(f"/api/v1/memory/{entry_id}", params={"project_id": beta}).status_code == 404
    assert client.post(f"/api/v1/memory/{entry_id}/rollback/1", params={"project_id": beta}).status_code == 404

    # Search is also project-scoped.
    assert client.get("/api/v1/memory/search", params={"q": "PostgreSQL", "project_id": beta}).json()["results"] == []
    assert len(client.get("/api/v1/memory/search", params={"q": "PostgreSQL", "project_id": alpha}).json()["results"]) == 1


def test_global_scope_is_shared_but_not_leaking_private_rows(client: TestClient) -> None:
    alpha = project(client, "Alpha")
    write(client, scope="global", project_id=None, title="Team standard", content="All work needs tests.")
    write(client, project_id=alpha, title="Alpha only", content="Secret alpha detail.")

    beta_entries = client.get("/api/v1/memory", params={"project_id": project(client, "Beta")}).json()["entries"]
    assert [entry["title"] for entry in beta_entries] == ["Team standard"]

    without_global = client.get(
        "/api/v1/memory", params={"project_id": alpha, "include_global": False}
    ).json()["entries"]
    assert [entry["title"] for entry in without_global] == ["Alpha only"]


def test_scope_validation_requires_bindings(client: TestClient) -> None:
    alpha = project(client)
    assert write(client, project_id=None).status_code == 422  # project scope needs a project
    assert write(client, project_id=alpha, scope="agent").status_code == 422
    assert write(client, project_id=alpha, scope="task").status_code == 422
    assert write(client, project_id="00000000-0000-0000-0000-000000000000").status_code == 422
    assert write(client, project_id=alpha, scope="nonsense").status_code == 422
    assert write(client, project_id=alpha, content="").status_code == 422


def test_keyed_memory_versions_and_rolls_back(client: TestClient) -> None:
    alpha = project(client)
    first = write(client, project_id=alpha, key="db-choice", title="Database", content="SQLite")
    entry_id = first.json()["entry"]["id"]
    assert first.json()["entry"]["version"] == 1

    second = write(client, project_id=alpha, key="db-choice", title="Database", content="PostgreSQL")
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["entry"]["version"] == 2
    assert second.json()["entry"]["id"] == entry_id

    detail = client.get(f"/api/v1/memory/{entry_id}", params={"project_id": alpha}).json()
    assert [item["version"] for item in detail["history"]] == [1, 2]

    rolled = client.post(f"/api/v1/memory/{entry_id}/rollback/1", params={"project_id": alpha})
    assert rolled.status_code == 200
    assert rolled.json()["entry"]["content"] == "SQLite"
    assert rolled.json()["entry"]["version"] == 3  # rollback is a new version, not a deletion

    assert client.post(f"/api/v1/memory/{entry_id}/rollback/99", params={"project_id": alpha}).status_code == 404


def test_search_ranking_and_exports(client: TestClient) -> None:
    alpha = project(client)
    write(client, project_id=alpha, title="Testing policy", content="Unit tests and integration tests required.")
    write(client, project_id=alpha, title="Deployment note", content="Blue-green deployment.")

    results = client.get("/api/v1/memory/search", params={"q": "integration tests", "project_id": alpha}).json()
    assert results["results"][0]["entry"]["title"] == "Testing policy"
    assert results["results"][0]["score"] > 0

    assert client.get("/api/v1/memory/search", params={"q": "   ", "project_id": alpha}).status_code == 422

    exported = client.get("/api/v1/memory/export", params={"project_id": alpha}).json()["entries"]
    assert {entry["title"] for entry in exported} == {"Testing policy", "Deployment note"}


def test_memory_writes_are_audited(client: TestClient) -> None:
    alpha = project(client)
    write(client, project_id=alpha)
    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "memory.created" in events

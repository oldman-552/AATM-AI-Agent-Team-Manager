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


# --- Context selection and summarization ---------------------------------


def seed(client: TestClient, project_id: str, **entries) -> dict:
    written = {}
    for key, payload in entries.items():
        body = {"project_id": project_id, **payload}
        response = client.post("/api/v1/memory", json=body)
        assert response.status_code == 201, response.text
        written[key] = response.json()["entry"]["id"] if "entry" in response.json() else response.json()["id"]
    return written


def test_context_respects_the_word_budget_and_explains_omissions(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Context"}).json()
    task = client.post("/api/v1/tasks", json={"title": "Scratch work", "project_id": project["id"]}).json()
    seed(
        client,
        project["id"],
        decision={
            "scope": "decision",
            "title": "Use SQLite for local storage",
            "content": "We decided SQLite is the default because setup must be zero. " * 12,
            "tags": ["database"],
        },
        note={
            "scope": "task",
            "task_id": task["id"],
            "title": "Scratch pad",
            "content": "Random working notes about the cache. " * 20,
        },
    )

    body = client.get(
        "/api/v1/memory/context", params={"project_id": project["id"], "word_budget": 60}
    ).json()
    assert body["budget"]["unit"] == "words"
    assert body["budget"]["words_used"] <= 60
    assert body["budget"]["words_remaining"] >= 0
    assert "not provider tokens" in body["budget"]["note"]

    # Everything is accounted for: selected + excluded == candidates.
    assert body["stats"]["selected"] + body["stats"]["excluded"] == body["stats"]["candidates"]
    for item in body["excluded"]:
        assert "over_budget" in item["reason"] or item["reason"] == "empty"
    # A summarized entry carries a real method, never a fabricated paraphrase.
    for item in body["selected"]:
        assert item["included_as"] in ("full", "summary")
        assert item["words"] > 0
        if item["included_as"] == "summary":
            assert item["summary_method"] == "extractive"


def test_context_prefers_decisions_over_scratch_notes(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Priority"}).json()
    task = client.post("/api/v1/tasks", json={"title": "Notes host", "project_id": project["id"]}).json()
    seed(
        client,
        project["id"],
        decision={"scope": "decision", "title": "Chosen database", "content": "SQLite is the default."},
        note={
            "scope": "task",
            "task_id": task["id"],
            "title": "Unrelated note",
            "content": "A note about something else entirely.",
        },
    )
    body = client.get(
        "/api/v1/memory/context", params={"project_id": project["id"], "word_budget": 10}
    ).json()
    assert body["selected"], body
    # The decision outranks the note when only one can fit.
    assert body["selected"][0]["scope"] == "decision"


def test_context_is_deterministic(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Stable"}).json()
    for index in range(4):
        seed(
            client,
            project["id"],
            **{f"e{index}": {"title": f"Entry {index}", "content": "Alpha beta gamma delta."}},
        )
    params = {"project_id": project["id"], "word_budget": 30, "q": "alpha"}
    first = client.get("/api/v1/memory/context", params=params).json()
    second = client.get("/api/v1/memory/context", params=params).json()
    assert [item["memory_id"] for item in first["selected"]] == [item["memory_id"] for item in second["selected"]]
    assert first["ranking"]["order"][0] == "relevance"


def test_context_rejects_bad_budgets_and_unknown_scopes(client: TestClient) -> None:
    assert client.get("/api/v1/memory/context", params={"word_budget": 5}).status_code == 422
    assert client.get("/api/v1/memory/context", params={"word_budget": 99999}).status_code == 422
    bad = client.get("/api/v1/memory/context", params={"scope": ["invented"]})
    assert bad.status_code == 422
    assert "Unknown scope" in bad.json()["detail"]


def test_summary_is_extractive_not_invented(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Summarize"}).json()
    content = (
        "The API returns 413 for oversized bodies. "
        "Sessions roll back before closing. "
        "Recovery is classified by cause."
    )
    entry = client.post(
        "/api/v1/memory",
        json={"project_id": project["id"], "title": "Reliability notes", "content": content},
    ).json()
    entry_id = entry["entry"]["id"] if "entry" in entry else entry["id"]

    summary = client.get(f"/api/v1/memory/summarize/{entry_id}", params={"max_words": 12}).json()
    assert summary["method"] == "extractive"
    assert summary["words"] <= 12
    # Every sentence in the summary must exist verbatim in the source.
    for sentence in summary["summary"].replace("…", "").split(". "):
        cleaned = sentence.strip().rstrip(".")
        if cleaned:
            assert cleaned in content, f"invented text: {cleaned!r}"
    assert client.get("/api/v1/memory/summarize/missing").status_code == 404


def test_context_can_filter_by_scope(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Scoped"}).json()
    task = client.post("/api/v1/tasks", json={"title": "Scoped task", "project_id": project["id"]}).json()
    seed(
        client,
        project["id"],
        decision={"scope": "decision", "title": "Decision A", "content": "Pick SQLite."},
        task={"scope": "task", "task_id": task["id"], "title": "Task T", "content": "Task-level note."},
    )
    only_tasks = client.get(
        "/api/v1/memory/context", params={"project_id": project["id"], "scope": ["task"]}
    ).json()
    assert [item["scope"] for item in only_tasks["selected"]] == ["task"]

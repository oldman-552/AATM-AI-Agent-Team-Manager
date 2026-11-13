"""Real Git workspace tests using throwaway repositories on disk."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.workspaces import (
    WorkspaceError,
    create_project_workspace,
    create_work_branch,
    init_local_repository,
    validate_branch_name,
    workspace_paths,
    workspace_status,
)


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AATM_WORKSPACES_ROOT", str(tmp_path / "workspaces"))
    app = create_app("sqlite://", allowed_hosts=["testserver"])
    with TestClient(app) as tc:
        yield tc


def new_project(client: TestClient, name: str = "Workspace Project") -> str:
    response = client.post("/api/v1/projects", json={"name": name, "description": "test"})
    assert response.status_code == 201
    return response.json()["id"]


def test_branch_names_are_validated() -> None:
    assert validate_branch_name("aatm/feature-1") == "aatm/feature-1"
    for bad in ("main", "master", "../escape", "-bad", "a b", "x" * 200, "refs//head", "feature/"):
        with pytest.raises(WorkspaceError):
            validate_branch_name(bad)


def test_workspace_path_cannot_escape_root(tmp_path) -> None:
    root = tmp_path / "root"
    paths = workspace_paths(root, "project-1", "../../etc")
    assert paths.root.resolve() in paths.project_dir.parents
    with pytest.raises(WorkspaceError):
        workspace_paths(root, "", "x")


def test_real_local_repository_workspace(tmp_path) -> None:
    source = tmp_path / "source"
    init_local_repository(source)
    paths = create_project_workspace(tmp_path / "ws", "proj-1", "Demo Project", source)
    assert (paths.project_dir / ".git").exists()
    assert paths.project_dir.name == "demo-project-proj-1"

    (paths.project_dir / "app.py").write_text("print('hi')\n", encoding="utf-8")
    status = workspace_status(paths)
    assert status["clean"] is False
    assert "app.py" in status["changed_files"]
    assert status["on_protected_branch"] is True
    assert status["branch"] == "main"

    branch = create_work_branch(paths, "aatm/feature-a")
    status = workspace_status(paths)
    assert status["branch"] == branch == "aatm/feature-a"
    assert status["on_protected_branch"] is False

    # The source repository is untouched by workspace activity.
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=source, capture_output=True, text=True
    ).stdout == ""


def test_workspace_api_lifecycle(client: TestClient) -> None:
    project_id = new_project(client)
    created = client.post(f"/api/v1/projects/{project_id}/workspace", json={})
    assert created.status_code == 201
    body = created.json()
    assert Path(body["workspace"]["workspace_path"]).exists()
    assert body["status"]["branch"] in {"main", "master"}

    duplicate = client.post(f"/api/v1/projects/{project_id}/workspace", json={})
    assert duplicate.status_code == 409

    branch = client.post(
        f"/api/v1/projects/{project_id}/workspace/branches",
        json={"branch": "aatm/task-12"},
    )
    assert branch.status_code == 201
    assert branch.json()["status"]["branch"] == "aatm/task-12"
    assert branch.json()["status"]["on_protected_branch"] is False

    protected = client.post(
        f"/api/v1/projects/{project_id}/workspace/branches", json={"branch": "main"}
    )
    assert protected.status_code == 422

    fetched = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert fetched["workspace"]["branch"] == "aatm/task-12"

    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "project.workspace_created" in events
    assert "project.workspace_branch_created" in events

    removed = client.delete(f"/api/v1/projects/{project_id}/workspace")
    assert removed.status_code == 200
    assert not Path(removed.json()["workspace_path"]).exists()
    assert client.get(f"/api/v1/projects/{project_id}/workspace").json()["workspace"] is None


def test_unknown_project_and_missing_workspace(client: TestClient) -> None:
    assert client.post("/api/v1/projects/missing/workspace", json={}).status_code == 404
    project_id = new_project(client)
    assert client.get(f"/api/v1/projects/{project_id}/workspace").json()["workspace"] is None
    assert client.post(
        f"/api/v1/projects/{project_id}/workspace/branches", json={"branch": "aatm/x"}
    ).status_code == 404


def test_invalid_local_source_is_rejected(client: TestClient, tmp_path) -> None:
    project_id = new_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/workspace",
        json={"local_source": str(tmp_path / "not-a-repo")},
    )
    assert response.status_code == 422
    assert "local Git repository" in response.json()["detail"]
    assert client.get(f"/api/v1/projects/{project_id}/workspace").json()["workspace"] is None


def test_workspace_creation_from_local_source_clones_history(client: TestClient, tmp_path) -> None:
    source = tmp_path / "upstream"
    init_local_repository(source)
    (source / "notes.txt").write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.txt"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "add notes"], cwd=source, check=True, capture_output=True)

    project_id = new_project(client)
    created = client.post(
        f"/api/v1/projects/{project_id}/workspace",
        json={"local_source": str(source), "branch": "aatm/from-source"},
    )
    assert created.status_code == 201
    workspace_path = Path(created.json()["workspace"]["workspace_path"])
    assert (workspace_path / "notes.txt").read_text(encoding="utf-8") == "content\n"
    assert created.json()["status"]["branch"] == "aatm/from-source"
    # Cloned repositories are local-only; no remote is configured by the test source.

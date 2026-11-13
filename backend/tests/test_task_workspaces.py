"""Same-project local executions get independent, inspectable Git worktrees."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.execution import LocalProcessExecutor
from app.main import create_app
from app.models import Task
from app.orchestrator import Orchestrator, OrchestratorConfig
from app.workspaces import init_local_repository, run_git


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AATM_WORKSPACES_ROOT", str(tmp_path / "workspace-root"))
    database_url = f"sqlite:///{(tmp_path / 'task-worktrees.sqlite3').as_posix()}"
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as test_client:
        yield test_client


def test_same_project_tasks_run_in_distinct_persisted_worktrees(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "source"
    init_local_repository(source)
    commands_dir = source / ".aatm"
    commands_dir.mkdir()
    script = "from pathlib import Path; import os; Path('task-output.txt').write_text(os.getcwd()); print(os.getcwd())"
    (commands_dir / "exec.json").write_text(
        json.dumps({"write": {"argv": ["python3", "-c", script]}}),
        encoding="utf-8",
    )
    run_git(["add", ".aatm/exec.json"], cwd=source)
    run_git(["commit", "--quiet", "-m", "Add safe local task command"], cwd=source)

    project_id = client.post("/api/v1/projects", json={"name": "Concurrent project"}).json()["id"]
    agent_id = client.post(
        "/api/v1/agents",
        json={"name": "Isolated worker", "role": "Backend Developer"},
    ).json()["id"]
    workspace_response = client.post(
        f"/api/v1/projects/{project_id}/workspace",
        json={"local_source": str(source)},
    )
    assert workspace_response.status_code == 201, workspace_response.text
    task_ids = []
    for index in range(2):
        response = client.post(
            "/api/v1/tasks",
            json={
                "title": f"Isolated task {index}",
                "project_id": project_id,
                "assigned_agent_id": agent_id,
                "acceptance_criteria": ["run:write"],
            },
        )
        assert response.status_code == 201, response.text
        task_ids.append(response.json()["id"])

    executor = LocalProcessExecutor(client.app.state.session_factory, allowed_programs=("python3",))
    with client.app.state.session_factory() as db:
        report = Orchestrator(executor, OrchestratorConfig(max_concurrency=2)).run_once(db)
        db.commit()
        task_paths = [Path(db.get(Task, task_id).output.strip()) for task_id in task_ids]

    assert set(report.started) == set(task_ids)
    assert set(report.completed) == set(task_ids)
    assert report.failed == []
    assert task_paths[0] != task_paths[1]
    assert all(path.is_absolute() for path in task_paths)
    assert all((path / "task-output.txt").read_text(encoding="utf-8") == str(path) for path in task_paths)
    project_workspace = Path(workspace_response.json()["workspace"]["workspace_path"])
    assert not (project_workspace / "task-output.txt").exists()
    assert all(".aatm-task-worktrees" in path.parts for path in task_paths)

    for task_id, path in zip(task_ids, task_paths, strict=True):
        inspection = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}")
        assert inspection.status_code == 200, inspection.text
        worktree = inspection.json()["worktree"]
        assert inspection.json()["available"] is True
        assert worktree["task_id"] == task_id
        assert worktree["worktree_path"] == str(path)
        assert worktree["base_commit"] == worktree["head_commit"]
        assert worktree["clean"] is False
        assert "task-output.txt" in worktree["changed_files"]
        assert worktree["content_included"] is False

    other_project_id = client.post("/api/v1/projects", json={"name": "Different project"}).json()["id"]
    cross_project = client.get(f"/api/v1/projects/{other_project_id}/workspace/tasks/{task_ids[0]}")
    assert cross_project.status_code == 404

    unexecuted = client.post(
        "/api/v1/tasks",
        json={"title": "Not yet executed", "project_id": project_id, "assigned_agent_id": agent_id},
    ).json()
    unavailable = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{unexecuted['id']}")
    assert unavailable.status_code == 200
    assert unavailable.json()["available"] is False
    assert unavailable.json()["worktree"] is None

    owner_file = project_workspace.parent / ".aatm-task-worktrees" / project_id / f"{task_ids[0]}.owner.json"
    owner_file.write_text("[]", encoding="utf-8")
    corrupted_owner = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_ids[0]}")
    assert corrupted_owner.status_code == 409

"""Same-project local executions get independent, inspectable Git worktrees."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.execution import LocalProcessExecutor
from app.main import create_app
from app.models import AuditEvent, ReviewRecord, Task
from app.run_lock import acquire_run_lock, release_run_lock
from app.orchestrator import Orchestrator, OrchestratorConfig
from app.task_workspaces import TASK_DIFF_PREVIEW_BYTES, integrate_approved_task_worktree, prepare_task_worktree
from app.worker_slots import acquire_worker_slots, release_worker_slots
from app.workspaces import WorkspaceError, init_local_repository, run_git


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AATM_WORKSPACES_ROOT", str(tmp_path / "workspace-root"))
    database_url = f"sqlite:///{(tmp_path / 'task-worktrees.sqlite3').as_posix()}"
    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as test_client:
        yield test_client


def test_workspace_creation_waits_for_worker_permits_to_clear(client: TestClient, tmp_path: Path) -> None:
    project_id = client.post("/api/v1/projects", json={"name": "Mutation gate"}).json()["id"]
    with client.app.state.session_factory() as db:
        assert acquire_worker_slots(db, "active-worker", limit=1, lease_seconds=60) == [1]

    endpoint = f"/api/v1/projects/{project_id}/workspace"
    blocked = client.post(endpoint, json={})
    assert blocked.status_code == 409
    assert "Another orchestrator run or workspace mutation" in blocked.json()["detail"]

    with client.app.state.session_factory() as db:
        assert release_worker_slots(db, "active-worker") == 1

    created = client.post(endpoint, json={})
    assert created.status_code == 201, created.text


def test_same_project_tasks_run_in_distinct_persisted_worktrees(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "source"
    init_local_repository(source)
    commands_dir = source / ".aatm"
    commands_dir.mkdir()
    script = "from pathlib import Path; import os; Path('task-output.txt').write_text(os.getcwd()); Path('README.md').write_text('task-specific\\n'); print(os.getcwd())"
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

        diff_response = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}/diff")
        assert diff_response.status_code == 200, diff_response.text
        preview = diff_response.json()["preview"]
        assert diff_response.json()["available"] is True
        assert "+task-specific" in preview["diff"]
        assert str(path) not in preview["diff"]  # untracked output is separate from the Git patch
        assert preview["untracked_included"] is True
        untracked_output = next(item for item in preview["untracked_files"] if item["path"] == "task-output.txt")
        assert untracked_output["status"] == "text"
        assert untracked_output["content"] == str(path)
        assert len(preview["diff"].encode("utf-8")) <= preview["max_bytes"]

    private_file = tmp_path / "outside-secret.txt"
    private_file.write_text("NEVER-RETURN-SECRET", encoding="utf-8")
    (task_paths[0] / "binary.dat").write_bytes(b"prefix" + bytes([0]) + b"NEVER-RETURN-SECRET")
    (task_paths[0] / "outside-link.txt").symlink_to(private_file)
    (task_paths[0] / "oversized.txt").write_text("o" * (TASK_DIFF_PREVIEW_BYTES // 8 + 1), encoding="utf-8")
    safe_preview = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_ids[0]}/diff").json()["preview"]
    untracked_status = {item["path"]: item["status"] for item in safe_preview["untracked_files"]}
    assert untracked_status["binary.dat"] == "binary"
    assert untracked_status["outside-link.txt"] == "symlink"
    assert untracked_status["oversized.txt"] == "too_large"
    assert next(item for item in safe_preview["untracked_files"] if item["path"] == "oversized.txt")["content"] is None
    assert "NEVER-RETURN-SECRET" not in str(safe_preview)

    for index in range(5):
        (task_paths[0] / f"new-{index}.txt").write_text("z" * 30_000, encoding="utf-8")
    aggregate_preview = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_ids[0]}/diff").json()["preview"]
    previewed_bytes = sum(
        len(item["content"].encode("utf-8"))
        for item in aggregate_preview["untracked_files"]
        if item["content"] is not None
    )
    assert previewed_bytes <= aggregate_preview["untracked_max_bytes"]
    assert aggregate_preview["untracked_truncated"] is True

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
    unavailable_diff = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{unexecuted['id']}/diff")
    assert unavailable_diff.status_code == 200
    assert unavailable_diff.json()["available"] is False
    assert unavailable_diff.json()["preview"] is None

    large_change = task_paths[0] / "README.md"
    large_change.write_text("x" * (TASK_DIFF_PREVIEW_BYTES * 2) + "\\n", encoding="utf-8")
    capped_diff = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_ids[0]}/diff")
    assert capped_diff.status_code == 200, capped_diff.text
    capped_preview = capped_diff.json()["preview"]
    assert capped_preview["truncated"] is True
    assert len(capped_preview["diff"].encode("utf-8")) <= TASK_DIFF_PREVIEW_BYTES

    owner_file = project_workspace.parent / ".aatm-task-worktrees" / project_id / f"{task_ids[0]}.owner.json"
    owner_file.write_text("[]", encoding="utf-8")
    corrupted_owner = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_ids[0]}")
    assert corrupted_owner.status_code == 409


def test_approved_task_commit_fast_forwards_only_clean_nonprotected_workspace(
    client: TestClient,
    tmp_path: Path,
) -> None:
    source = tmp_path / "integration-source"
    init_local_repository(source)
    project_id = client.post("/api/v1/projects", json={"name": "Review integration"}).json()["id"]
    workspace_response = client.post(
        f"/api/v1/projects/{project_id}/workspace",
        json={"local_source": str(source)},
    )
    assert workspace_response.status_code == 201, workspace_response.text
    workspace_path = Path(workspace_response.json()["workspace"]["workspace_path"])
    branch_response = client.post(
        f"/api/v1/projects/{project_id}/workspace/branches",
        json={"branch": "review/task-integration"},
    )
    assert branch_response.status_code == 201, branch_response.text

    assigned_agent_id = client.post(
        "/api/v1/agents",
        json={"name": "Task author", "role": "Developer"},
    ).json()["id"]
    reviewer_agent_id = client.post(
        "/api/v1/agents",
        json={"name": "Independent reviewer", "role": "Reviewer"},
    ).json()["id"]
    task_response = client.post(
        "/api/v1/tasks",
        json={"title": "Reviewed integration", "project_id": project_id, "assigned_agent_id": assigned_agent_id},
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["id"]
    task_worktree = prepare_task_worktree(workspace_path.parent, workspace_path, project_id, task_id)
    assert task_worktree is not None
    (task_worktree / "README.md").write_text("reviewed and approved\n", encoding="utf-8")
    run_git(["config", "user.email", "reviewer@localhost"], cwd=task_worktree)
    run_git(["config", "user.name", "AATM Reviewer"], cwd=task_worktree)
    run_git(["add", "README.md"], cwd=task_worktree)
    run_git(["commit", "--quiet", "-m", "Reviewed task change"], cwd=task_worktree)
    reviewed_head = run_git(["rev-parse", "HEAD"], cwd=task_worktree)

    endpoint = f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}/integrate"
    refused = client.post(endpoint)
    assert refused.status_code == 409
    assert run_git(["rev-parse", "HEAD"], cwd=workspace_path) != reviewed_head

    for target_state, key, extra in [
        ("running", "integration-start", {"note": "Execution started."}),
        ("completed", "integration-complete", {"note": "Task commit prepared.", "output": "commit prepared"}),
        ("reviewing", "integration-review-start", {"note": "Ready for independent review."}),
    ]:
        transition = client.patch(
            f"/api/v1/tasks/{task_id}/state",
            json={"target_state": target_state, "idempotency_key": key, **extra},
        )
        assert transition.status_code == 200, transition.text

    preview = client.get(f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}/diff")
    assert preview.status_code == 200, preview.text
    assert "+reviewed and approved" in preview.json()["preview"]["diff"]
    approved = client.post(
        f"/api/v1/tasks/{task_id}/reviews",
        json={
            "reviewer_agent_id": reviewer_agent_id,
            "verdict": "approved",
            "summary": "Reviewed task diff before integration.",
            "checks": [{"check": "Capped diff inspected", "result": "pass"}],
            "idempotency_key": "integration-review-approved",
        },
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["review"]["task_worktree_head"] == reviewed_head
    (task_worktree / "post-review-change.txt").write_text("not reviewed\n", encoding="utf-8")
    run_git(["add", "post-review-change.txt"], cwd=task_worktree)
    run_git(["commit", "--quiet", "-m", "Change after review"], cwd=task_worktree)
    stale_review = client.post(endpoint)
    assert stale_review.status_code == 409
    assert "current task-worktree commit" in stale_review.json()["detail"]
    run_git(["reset", "--hard", reviewed_head], cwd=task_worktree)
    with client.app.state.session_factory() as db:
        assert acquire_run_lock(db, "simulated-orchestrator", lease_seconds=120)
    locked = client.post(endpoint)
    assert locked.status_code == 409
    with client.app.state.session_factory() as db:
        assert release_run_lock(db, "simulated-orchestrator")
    (task_worktree / "unreviewed.txt").write_text("not committed\n", encoding="utf-8")
    dirty_task = client.post(endpoint)
    assert dirty_task.status_code == 409
    assert "must be clean" in dirty_task.json()["detail"]
    (task_worktree / "unreviewed.txt").unlink()

    hook_marker = tmp_path / "post-merge-hook-ran"
    hook_path = workspace_path / ".git" / "hooks" / "post-merge"
    hook_path.write_text(f"#!/bin/sh\ntouch '{hook_marker}'\n", encoding="utf-8")
    hook_path.chmod(0o755)
    integrated = client.post(endpoint)
    assert integrated.status_code == 200, integrated.text
    result = integrated.json()
    assert result["integrated"] is True
    assert result["already_integrated"] is False
    assert result["branch"] == "review/task-integration"
    assert result["head_commit"] == reviewed_head
    assert (workspace_path / "README.md").read_text(encoding="utf-8") == "reviewed and approved\n"
    assert not hook_marker.exists()
    assert run_git(["status", "--porcelain"], cwd=workspace_path) == ""
    assert run_git(["status", "--porcelain"], cwd=task_worktree) == ""

    repeated = client.post(endpoint)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["already_integrated"] is True
    with client.app.state.session_factory() as db:
        events = db.query(AuditEvent).filter_by(entity_type="task", entity_id=task_id).all()
        assert [event.event_type for event in events].count("task.worktree_integrated") == 1


def test_task_integration_rejects_dirty_project_workspace(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "dirty-integration-source"
    init_local_repository(source)
    project_id = client.post("/api/v1/projects", json={"name": "Dirty integration"}).json()["id"]
    workspace_response = client.post(
        f"/api/v1/projects/{project_id}/workspace",
        json={"local_source": str(source)},
    )
    workspace_path = Path(workspace_response.json()["workspace"]["workspace_path"])
    client.post(f"/api/v1/projects/{project_id}/workspace/branches", json={"branch": "review/dirty"})
    task_id = client.post(
        "/api/v1/tasks",
        json={"title": "Dirty integration guard", "project_id": project_id},
    ).json()["id"]
    task_worktree = prepare_task_worktree(workspace_path.parent, workspace_path, project_id, task_id)
    assert task_worktree is not None
    (task_worktree / "README.md").write_text("committed\n", encoding="utf-8")
    run_git(["config", "user.email", "reviewer@localhost"], cwd=task_worktree)
    run_git(["config", "user.name", "AATM Reviewer"], cwd=task_worktree)
    run_git(["add", "README.md"], cwd=task_worktree)
    run_git(["commit", "--quiet", "-m", "Reviewed change"], cwd=task_worktree)
    with client.app.state.session_factory() as db:
        task = db.get(Task, task_id)
        assert task is not None
        task.state = "approved"
        db.add(ReviewRecord(
            task_id=task_id,
            verdict="approved",
            summary="Test review snapshot",
            checks=[{"check": "Diff reviewed", "result": "pass"}],
            task_worktree_head=run_git(["rev-parse", "HEAD"], cwd=task_worktree),
            idempotency_key="test-review-before-dirty-check",
        ))
        db.commit()
    (workspace_path / "local-uncommitted.txt").write_text("preserve me\n", encoding="utf-8")

    response = client.post(f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}/integrate")
    assert response.status_code == 409
    assert (workspace_path / "local-uncommitted.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert "must be clean" in response.json()["detail"]

    (workspace_path / "local-uncommitted.txt").unlink()
    (task_worktree / "binary.dat").write_bytes(b"binary" + bytes([0]) + b"payload")
    run_git(["add", "binary.dat"], cwd=task_worktree)
    run_git(["commit", "--quiet", "-m", "Binary change requires manual review"], cwd=task_worktree)
    base_commit = run_git(["merge-base", "HEAD", run_git(["rev-parse", "HEAD"], cwd=task_worktree)], cwd=workspace_path)
    task_head = run_git(["rev-parse", "HEAD"], cwd=task_worktree)
    numstat = run_git(["diff", "--numstat", "-z", base_commit, task_head], cwd=workspace_path)
    assert any(line.startswith("-\t-\t") for line in numstat.split("\0"))
    with client.app.state.session_factory() as db:
        db.add(ReviewRecord(
            task_id=task_id,
            verdict="approved",
            summary="Binary change reviewed for rejection behavior",
            checks=[{"check": "Manual handling required", "result": "pass"}],
            task_worktree_head=task_head,
            idempotency_key="test-review-binary-change",
        ))
        db.commit()
    binary_response = client.post(f"/api/v1/projects/{project_id}/workspace/tasks/{task_id}/integrate")
    assert binary_response.status_code == 409
    assert "Binary" in binary_response.json()["detail"]
    assert run_git(["rev-parse", "HEAD"], cwd=workspace_path) != run_git(["rev-parse", "HEAD"], cwd=task_worktree)


def test_task_integration_refuses_protected_branch(tmp_path: Path) -> None:
    root = tmp_path / "protected-root"
    source = root / "project"
    init_local_repository(source)
    base = run_git(["rev-parse", "HEAD"], cwd=source)
    task_worktree = prepare_task_worktree(root, source, "protected-project", "protected-task")
    assert task_worktree is not None
    (task_worktree / "README.md").write_text("reviewed\n", encoding="utf-8")
    run_git(["config", "user.email", "reviewer@localhost"], cwd=task_worktree)
    run_git(["config", "user.name", "AATM Reviewer"], cwd=task_worktree)
    run_git(["add", "README.md"], cwd=task_worktree)
    run_git(["commit", "--quiet", "-m", "Approved work"], cwd=task_worktree)
    task_head = run_git(["rev-parse", "HEAD"], cwd=task_worktree)

    with pytest.raises(WorkspaceError, match="protected branch"):
        integrate_approved_task_worktree(
            root,
            source,
            "protected-project",
            "protected-task",
            approved_head=task_head,
        )
    assert run_git(["rev-parse", "HEAD"], cwd=source) == base

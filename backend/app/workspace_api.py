"""Project workspace endpoints for isolated local Git workspaces.

Inspection is read-only. Task commits can be explicitly fast-forwarded only
through the separate approval-gated integration endpoint; no endpoint pushes,
fetches from a network, or deletes workspace data.
"""

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.audit import add_event
from app.models import Project, ProjectWorkspace, ReviewRecord, Task
from app.run_lock import acquire_run_lock, release_run_lock
from app.task_workspaces import integrate_approved_task_worktree, inspect_task_worktree, preview_task_worktree_diff
from app.workspaces import (
    WorkspaceError,
    create_project_workspace,
    create_work_branch,
    remove_workspace,
    stored_workspace_paths,
    validate_branch_name,
    workspace_status,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/workspace")


def default_workspace_root() -> Path:
    """`AATM_WORKSPACES_ROOT` or `~/.aatm/workspaces` — never the repository itself."""
    configured = os.environ.get("AATM_WORKSPACES_ROOT")
    if configured:
        return Path(configured).expanduser()
    home = Path(os.environ.get("AATM_HOME", Path.home() / ".aatm")).expanduser()
    return home / "workspaces"


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_source: str | None = Field(default=None, max_length=1000)
    branch: str | None = Field(default=None, max_length=121)


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch: str = Field(min_length=1, max_length=121)


def _workspace_row(db: Session, project_id: str) -> ProjectWorkspace | None:
    return db.scalar(select(ProjectWorkspace).where(ProjectWorkspace.project_id == project_id))


def _acquire_workspace_mutation_lock(db: Session) -> str:
    owner = f"workspace-mutation-{uuid4()}"
    try:
        acquired = acquire_run_lock(db, owner, lease_seconds=120)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not acquire the shared workspace mutation lock.") from exc
    if not acquired:
        raise HTTPException(status_code=409, detail="Another orchestrator run or workspace mutation is active for this database.")
    return owner


def _release_workspace_mutation_lock(db: Session, owner: str) -> None:
    db.rollback()
    release_run_lock(db, owner)


@router.get("")
def get_workspace(project_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    row = _workspace_row(db, project_id)
    if row is None:
        return {"workspace": None, "note": "No workspace has been created for this project."}
    try:
        paths = stored_workspace_paths(row.root_path, row.workspace_path)
        status = workspace_status(paths)
    except WorkspaceError as exc:
        return {
            "workspace": {
                "id": row.id,
                "project_id": row.project_id,
                "workspace_path": row.workspace_path,
                "root_path": row.root_path,
                "branch": row.branch,
                "status": row.status,
            },
            "status": None,
            "error": str(exc),
        }
    return {
        "workspace": {
            "id": row.id,
            "project_id": row.project_id,
            "workspace_path": row.workspace_path,
            "root_path": row.root_path,
            "branch": row.branch,
            "status": row.status,
        },
        "status": status,
    }


@router.get("/tasks/{task_id}")
def inspect_task_workspace(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Inspect a task's owned Git worktree without returning file contents."""
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        # Do not reveal whether another project's task identifier exists.
        raise HTTPException(status_code=404, detail="Task not found in this project.")
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")
    try:
        paths = stored_workspace_paths(row.root_path, row.workspace_path)
        worktree = inspect_task_worktree(paths.root, paths.project_dir, project_id, task_id)
    except WorkspaceError as exc:
        raise HTTPException(status_code=409, detail=f"Task workspace cannot be inspected safely: {exc}") from exc
    return {
        "task_id": task_id,
        "task_state": task.state,
        "available": worktree is not None,
        "worktree": worktree,
        "note": (
            "Task worktree is available for local review; no file contents are included and no changes are merged."
            if worktree is not None
            else "No AATM-owned task worktree exists for this task."
        ),
    }


@router.get("/tasks/{task_id}/diff")
def preview_task_diff(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Return a strictly capped, read-only patch preview for one task."""
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found in this project.")
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")
    try:
        paths = stored_workspace_paths(row.root_path, row.workspace_path)
        preview = preview_task_worktree_diff(paths.root, paths.project_dir, project_id, task_id)
    except WorkspaceError as exc:
        raise HTTPException(status_code=409, detail=f"Task diff cannot be inspected safely: {exc}") from exc
    return {
        "task_id": task_id,
        "available": preview is not None,
        "preview": preview,
        "note": (
            "Capped tracked patch plus separately bounded safe untracked UTF-8 text previews; no changes are applied."
            if preview is not None
            else "No AATM-owned task worktree exists for this task."
        ),
    }


@router.post("/tasks/{task_id}/integrate")
def integrate_task_changes(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Explicitly fast-forward an independently approved task commit.

    This is intentionally not part of diff preview. It requires an approved
    task, a clean source workspace on a non-protected branch, and a clean task
    worktree containing only a reviewable committed descendant of its base.
    """
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found in this project.")
    if task.state != "approved":
        raise HTTPException(status_code=409, detail="Task must pass independent review and be approved before integration.")
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")

    owner = _acquire_workspace_mutation_lock(db)
    try:
        try:
            paths = stored_workspace_paths(row.root_path, row.workspace_path)
            worktree = inspect_task_worktree(paths.root, paths.project_dir, project_id, task_id)
            current_head = worktree.get("head_commit") if worktree is not None else None
            if not isinstance(current_head, str):
                raise HTTPException(status_code=409, detail="No valid task-worktree HEAD is available for integration.")
            review = db.scalar(
                select(ReviewRecord)
                .where(
                    ReviewRecord.task_id == task_id,
                    ReviewRecord.verdict == "approved",
                    ReviewRecord.task_worktree_head == current_head,
                )
                .order_by(ReviewRecord.created_at.desc())
                .limit(1)
            )
            if review is None:
                raise HTTPException(
                    status_code=409,
                    detail="Independent approval must be recorded against the current task-worktree commit before integration.",
                )
            result = integrate_approved_task_worktree(
                paths.root,
                paths.project_dir,
                project_id,
                task_id,
                approved_head=current_head,
            )
        except WorkspaceError as exc:
            raise HTTPException(status_code=409, detail=f"Task changes cannot be integrated safely: {exc}") from exc
        if not result["already_integrated"]:
            add_event(
                db,
                "task",
                task_id,
                "task.worktree_integrated",
                f"Approved task commit fast-forwarded into project branch {result['branch']} at {result['head_commit']}.",
            )
            db.commit()
        return {"task_id": task_id, **result}
    finally:
        _release_workspace_mutation_lock(db, owner)


@router.post("", status_code=201)
def create_workspace(
    project_id: str,
    payload: WorkspaceCreate,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if _workspace_row(db, project_id) is not None:
        raise HTTPException(status_code=409, detail="This project already has a workspace.")

    root = default_workspace_root()
    try:
        paths = create_project_workspace(
            root,
            project_id,
            project.name,
            Path(payload.local_source) if payload.local_source else None,
        )
        branch = payload.branch
        if branch:
            branch = create_work_branch(paths, branch)
    except WorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = ProjectWorkspace(
        project_id=project_id,
        root_path=str(paths.root),
        workspace_path=str(paths.project_dir),
        branch=branch,
        status="active",
    )
    db.add(row)
    add_event(db, "project", project_id, "project.workspace_created", f"Workspace created for project: {project.name}")
    db.commit()
    db.refresh(row)
    return {
        "workspace": {
            "id": row.id,
            "project_id": row.project_id,
            "workspace_path": row.workspace_path,
            "root_path": row.root_path,
            "branch": row.branch,
            "status": row.status,
        },
        "status": workspace_status(paths),
    }


@router.post("/branches", status_code=201)
def create_branch(
    project_id: str,
    payload: BranchCreate,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")
    owner = _acquire_workspace_mutation_lock(db)
    try:
        try:
            paths = stored_workspace_paths(row.root_path, row.workspace_path)
            name = validate_branch_name(payload.branch)
            create_work_branch(paths, name)
            status = workspace_status(paths)
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        row.branch = name
        add_event(db, "project", project_id, "project.workspace_branch_created", f"Work branch created: {name}")
        db.commit()
        return {"branch": name, "status": status}
    finally:
        _release_workspace_mutation_lock(db, owner)


@router.delete("", status_code=200)
def delete_workspace(project_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    """Explicit, audited local cleanup guarded by a strict root check.

    This deletes only the AATM-created workspace directory; it never touches the
    project's source repository and never runs destructive Git commands.
    """
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")
    owner = _acquire_workspace_mutation_lock(db)
    try:
        try:
            paths = stored_workspace_paths(row.root_path, row.workspace_path)
            remove_workspace(paths)
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        db.delete(row)
        add_event(db, "project", project_id, "project.workspace_removed", "Workspace directory removed after explicit request.")
        db.commit()
        return {"removed": True, "workspace_path": str(paths.project_dir)}
    finally:
        _release_workspace_mutation_lock(db, owner)

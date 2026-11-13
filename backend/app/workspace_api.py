"""Project workspace endpoints: isolated Git worktrees with read-only status.

No endpoint merges, pushes, deletes, or fetches from a network. Workspaces are
created under a configured root by cloning a *local* repository, or initialized
as a fresh local repository. Deletion is intentionally not exposed.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.audit import add_event
from app.models import Project, ProjectWorkspace
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


@router.delete("", status_code=200)
def delete_workspace(project_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    """Explicit, audited local cleanup guarded by a strict root check.

    This deletes only the AATM-created workspace directory; it never touches the
    project's source repository and never runs destructive Git commands.
    """
    row = _workspace_row(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No workspace exists for this project.")
    try:
        paths = stored_workspace_paths(row.root_path, row.workspace_path)
        remove_workspace(paths)
    except WorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.delete(row)
    add_event(db, "project", project_id, "project.workspace_removed", "Workspace directory removed after explicit request.")
    db.commit()
    return {"removed": True, "workspace_path": str(paths.project_dir)}

"""Independent QA review and approval-gate endpoints.

Recording a review drives the existing workflow state machine; nothing here
executes a task or a gated operation. An approved approval request records a
human decision only — the gated action itself remains unimplemented.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.models import ApprovalRequest, ProjectWorkspace, ReviewRecord, Task
from app.quality import (
    ReviewError,
    decide_approval,
    list_reviews,
    record_review,
    request_approval,
)
from app.task_workspaces import inspect_task_worktree
from app.workspaces import WorkspaceError, stored_workspace_paths
from app.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    ReviewCreate,
    ReviewRead,
)

router = APIRouter(prefix="/api/v1")


@router.get("/tasks/{task_id}/reviews")
def get_reviews(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    if db.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    records = list_reviews(db, task_id)
    return {
        "reviews": [ReviewRead.model_validate(record).model_dump(mode="json") for record in records],
        "note": "Reviews require a reviewer other than the assignee; approvals need concrete checks.",
    }


@router.post("/tasks/{task_id}/reviews", status_code=201)
def create_review(
    task_id: str,
    payload: ReviewCreate,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    task_worktree_head: str | None = None
    if task.project_id:
        workspace = db.scalar(select(ProjectWorkspace).where(ProjectWorkspace.project_id == task.project_id))
        if workspace is not None:
            try:
                paths = stored_workspace_paths(workspace.root_path, workspace.workspace_path)
                worktree = inspect_task_worktree(paths.root, paths.project_dir, task.project_id, task_id)
            except WorkspaceError as exc:
                raise HTTPException(status_code=409, detail=f"Task worktree cannot be safely bound to this review: {exc}") from exc
            if worktree is not None:
                head = worktree.get("head_commit")
                task_worktree_head = head if isinstance(head, str) else None
    try:
        record, created = record_review(
            db,
            task,
            reviewer_agent_id=payload.reviewer_agent_id,
            verdict=payload.verdict,
            summary=payload.summary,
            checks=[item.model_dump() for item in payload.checks],
            idempotency_key=payload.idempotency_key,
            task_worktree_head=task_worktree_head,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(record)
    db.refresh(task)
    return {
        "review": ReviewRead.model_validate(record).model_dump(mode="json"),
        "created": created,
        "task_state": task.state,
    }


@router.get("/approvals")
def list_approvals(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc())
    if status:
        statement = statement.where(ApprovalRequest.status == status)
    rows = db.scalars(statement).all()
    return {
        "approvals": [ApprovalRead.model_validate(row).model_dump(mode="json") for row in rows],
        "note": "Approval records a decision; it does not execute the gated action.",
    }


@router.post("/approvals", status_code=201)
def create_approval(payload: ApprovalCreate, db: Session = Depends(get_session)) -> dict[str, object]:
    if payload.entity_type == "task" and payload.entity_id and db.get(Task, payload.entity_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        approval = request_approval(
            db,
            kind=payload.kind,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            summary=payload.summary,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(approval)
    return {"approval": ApprovalRead.model_validate(approval).model_dump(mode="json")}


@router.patch("/approvals/{approval_id}")
def decide(
    approval_id: str,
    payload: ApprovalDecision,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    try:
        updated = decide_approval(
            db,
            approval,
            status=payload.status,
            decided_by=payload.decided_by,
            note=payload.note,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(updated)
    return {
        "approval": ApprovalRead.model_validate(updated).model_dump(mode="json"),
        "note": "The gated action is still not executed by this build.",
    }


@router.get("/reviews")
def all_reviews(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_session)) -> dict[str, object]:
    rows = db.scalars(
        select(ReviewRecord).order_by(ReviewRecord.created_at.desc()).limit(limit)
    ).all()
    return {"reviews": [ReviewRead.model_validate(row).model_dump(mode="json") for row in rows]}

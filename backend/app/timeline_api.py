"""Execution timeline and cancellation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.api import get_session
from app.cancellation import CancelError, honour_all, honour_cancel, pending_cancellations, request_cancel, withdraw_cancel
from app.models import Project, Task
from app.timeline import project_timeline, task_timeline

router = APIRouter(prefix="/api/v1")


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    requested_by: str = Field(default="local-user", max_length=120)


def _task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("/tasks/{task_id}/timeline")
def get_task_timeline(
    task_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    return task_timeline(db, _task(db, task_id), limit=limit)


@router.get("/projects/{project_id}/timeline")
def get_project_timeline(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project_timeline(db, project_id, limit=limit)


@router.post("/tasks/{task_id}/cancel")
def cancel_request(task_id: str, payload: CancelRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    task = _task(db, task_id)
    try:
        updated = request_cancel(db, task, reason=payload.reason, requested_by=payload.requested_by)
    except CancelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {
        "task_id": updated.id,
        "cancel_requested_at": updated.cancel_requested_at.isoformat() if updated.cancel_requested_at else None,
        "cancel_reason": updated.cancel_reason,
        "state": updated.state,
        "note": "Recorded as intent. The orchestrator honours it at the next safe boundary.",
    }


@router.delete("/tasks/{task_id}/cancel")
def cancel_withdraw(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    task = _task(db, task_id)
    try:
        withdraw_cancel(db, task)
    except CancelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"task_id": task.id, "cancel_requested_at": None, "state": task.state}


@router.post("/tasks/{task_id}/cancel/apply")
def cancel_apply(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    """Honour this task's pending cancellation immediately (an operator action)."""
    task = _task(db, task_id)
    try:
        result = honour_cancel(db, task)
    except CancelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"task_id": task.id, **result}


@router.get("/cancellations")
def list_pending(db: Session = Depends(get_session)) -> dict[str, object]:
    return {
        "pending": [
            {
                "task_id": task.id,
                "title": task.title,
                "state": task.state,
                "reason": task.cancel_reason,
                "requested_at": task.cancel_requested_at.isoformat() if task.cancel_requested_at else None,
            }
            for task in pending_cancellations(db)
        ]
    }


@router.post("/cancellations/apply")
def apply_all(db: Session = Depends(get_session)) -> dict[str, object]:
    result = honour_all(db)
    db.commit()
    return result

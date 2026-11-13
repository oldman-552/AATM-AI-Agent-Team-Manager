"""Durable task checkpoints and resume guidance."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.checkpoints import (
    CheckpointError,
    CheckpointWrite,
    checkpoint_payload,
    cleanup_checkpoints,
    latest_checkpoint,
    list_checkpoints,
    resume_plan,
    write_checkpoint,
)
from app.models import Task

router = APIRouter(prefix="/api/v1/tasks")


class CheckpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    state: dict = Field(default_factory=dict)
    note: str = Field(default="", max_length=500)


def _task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("/{task_id}/checkpoints")
def get_checkpoints(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    task = _task(db, task_id)
    return {
        "task_id": task.id,
        "checkpoints": [checkpoint_payload(item) for item in list_checkpoints(db, task_id)],
    }


@router.post("/{task_id}/checkpoints", status_code=201)
def add_checkpoint(task_id: str, payload: CheckpointCreate, db: Session = Depends(get_session)) -> dict[str, object]:
    task = _task(db, task_id)
    try:
        checkpoint = write_checkpoint(db, task, CheckpointWrite(**payload.model_dump()))
    except CheckpointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"checkpoint": checkpoint_payload(checkpoint), "created": True}


@router.get("/{task_id}/resume-plan")
def get_resume_plan(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    task = _task(db, task_id)
    return resume_plan(db, task)


@router.delete("/{task_id}/checkpoints")
def prune_checkpoints(
    task_id: str,
    keep: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    _task(db, task_id)
    try:
        removed = cleanup_checkpoints(db, keep=keep, task_id=task_id)
    except CheckpointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    latest = latest_checkpoint(db, task_id)
    return {"removed": removed, "latest": checkpoint_payload(latest) if latest else None}

"""HTTP endpoints for the local task state machine and ready queue."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import get_session
from app.models import Task
from app.schemas import TaskRead, TaskStateChange
from app.workflow import (
    ALLOWED_TRANSITIONS,
    DEPENDENCY_SATISFIED_STATES,
    EVIDENCE_REQUIRED_STATES,
    WorkflowError,
    allowed_next_states,
    ready_tasks,
    task_transitions,
    transition_history,
    transition_task,
)

router = APIRouter(prefix="/api/v1")


def _get_task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("/tasks/workflow")
def describe_workflow() -> dict[str, object]:
    """Expose the server-side transition map so the UI cannot invent states."""
    return {
        "transitions": {state: list(targets) for state, targets in ALLOWED_TRANSITIONS.items()},
        "dependency_satisfied_states": sorted(DEPENDENCY_SATISFIED_STATES),
        "evidence_required_states": sorted(EVIDENCE_REQUIRED_STATES),
        "note": "Server-side workflow definition; no execution is performed by this endpoint.",
    }


@router.get("/tasks/ready")
def list_ready_tasks(db: Session = Depends(get_session), limit: int = 100) -> dict[str, object]:
    """Assigned tasks whose dependencies are satisfied. No execution occurs."""
    tasks = ready_tasks(db, min(max(limit, 1), 500))
    return {
        "tasks": [TaskRead.model_validate(task).model_dump(mode="json") for task in tasks],
        "note": "This is a state-based ready queue, not an executing scheduler. No provider or shell work is started.",
    }


@router.get("/tasks/{task_id}/transitions")
def list_task_transitions(task_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    _get_task(db, task_id)
    return {"transitions": transition_history(task_transitions(db, task_id))}


@router.patch("/tasks/{task_id}/state")
def change_task_state(
    task_id: str,
    payload: TaskStateChange,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Validate and persist one workflow transition with replay protection."""
    task = _get_task(db, task_id)
    try:
        updated, created = transition_task(
            db,
            task,
            target_state=payload.target_state,
            idempotency_key=payload.idempotency_key,
            note=payload.note,
            output=payload.output,
            error=payload.error,
        )
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(updated)
    return {
        "task": TaskRead.model_validate(updated).model_dump(mode="json"),
        "transition_created": created,
        "allowed_next_states": allowed_next_states(updated.state),
    }

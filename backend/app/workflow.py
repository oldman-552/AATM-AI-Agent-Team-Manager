"""Local task state machine: explicit transitions, dependency gating, replay safety.

This is a *workflow state* service, not an executor. It never calls an AI
provider, runs a shell command, or pretends a task was executed. All state
changes are persisted with observable audit events and idempotency keys.
"""

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Task, TaskTransition
from app.schemas import TaskState

ALLOWED_TRANSITIONS: dict[TaskState, tuple[TaskState, ...]] = {
    "pending": ("assigned", "cancelled"),
    "assigned": ("pending", "running", "cancelled"),
    "running": ("waiting", "completed", "failed", "cancelled"),
    "waiting": ("running", "failed", "cancelled"),
    "completed": ("reviewing", "rework_required"),
    "failed": ("assigned", "rework_required", "cancelled"),
    "reviewing": ("approved", "rework_required"),
    "rework_required": ("assigned", "cancelled"),
    "approved": (),
    "cancelled": (),
}

DEPENDENCY_SATISFIED_STATES = frozenset({"completed", "approved"})
EVIDENCE_REQUIRED_STATES = frozenset({"failed", "approved", "rework_required"})
PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class WorkflowError(ValueError):
    """A safe, user-facing workflow validation failure."""


def allowed_next_states(state: str) -> list[str]:
    return list(ALLOWED_TRANSITIONS.get(state, ()))  # type: ignore[arg-type]


def dependencies_satisfied(db: Session, task: Task) -> tuple[bool, list[str]]:
    """Return (satisfied, blocking dependency ids)."""
    dependency_ids = [str(item) for item in (task.dependencies or [])]
    if not dependency_ids:
        return True, []
    rows = db.scalars(select(Task).where(Task.id.in_(dependency_ids))).all()
    states = {row.id: row.state for row in rows}
    blocking = [
        dependency_id
        for dependency_id in dependency_ids
        if states.get(dependency_id) not in DEPENDENCY_SATISFIED_STATES
    ]
    return not blocking, blocking


def ready_tasks(db: Session, limit: int = 100) -> list[Task]:
    """Assigned tasks whose dependencies are satisfied, ordered by priority."""
    candidates = list(
        db.scalars(
            select(Task).where(
                Task.state == "assigned",
                Task.assigned_agent_id.is_not(None),
            )
        ).all()
    )
    ready = [task for task in candidates if dependencies_satisfied(db, task)[0]]
    ready.sort(key=lambda task: (PRIORITY_ORDER.get(task.priority, 9), task.created_at))
    return ready[:limit]


def task_transitions(db: Session, task_id: str, limit: int = 100) -> list[TaskTransition]:
    return list(
        db.scalars(
            select(TaskTransition)
            .where(TaskTransition.task_id == task_id)
            .order_by(TaskTransition.created_at.asc())
            .limit(limit)
        ).all()
    )


def transition_task(
    db: Session,
    task: Task,
    *,
    target_state: TaskState,
    idempotency_key: str,
    note: str = "",
    output: str | None = None,
    error: str | None = None,
) -> tuple[Task, bool]:
    """Apply one validated transition. Returns (task, created).

    A repeated ``idempotency_key`` for the same task replays the original
    outcome without creating a second transition or audit event.
    """
    key = idempotency_key.strip()
    if not key or len(key) > 160:
        raise WorkflowError("An idempotency key of 1–160 characters is required.")

    existing = db.scalar(
        select(TaskTransition).where(
            TaskTransition.task_id == task.id,
            TaskTransition.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.to_state != target_state:
            raise WorkflowError("This idempotency key was already used for a different target state.")
        return task, False

    current = task.state
    allowed = ALLOWED_TRANSITIONS.get(current, ())  # type: ignore[arg-type]
    if target_state == current:
        raise WorkflowError(f"Task is already in state '{current}'.")
    if target_state not in allowed:
        raise WorkflowError(
            f"Transition '{current}' → '{target_state}' is not allowed. "
            f"Allowed: {', '.join(allowed) or 'none (terminal state)'}."
        )
    if target_state == "running":
        if task.assigned_agent_id is None:
            raise WorkflowError("A task must be assigned before it can be started.")
        satisfied, blocking = dependencies_satisfied(db, task)
        if not satisfied:
            raise WorkflowError(
                "Dependencies are not complete: " + ", ".join(blocking) + "."
            )
    if target_state in EVIDENCE_REQUIRED_STATES and not note.strip():
        raise WorkflowError(
            f"Evidence is required for '{target_state}' transitions; provide a note."
        )

    previous = current
    task.state = target_state
    if target_state in {"rework_required", "failed"}:
        task.retry_count = int(task.retry_count or 0) + 1
    if output is not None:
        task.output = output
    if error is not None:
        task.error = error
    else:
        task.error = None if target_state not in {"failed", "rework_required"} else (error or note)
    if target_state in {"completed", "approved", "cancelled"}:
        task.error = None

    db.add(
        TaskTransition(
            task_id=task.id,
            from_state=previous,
            to_state=target_state,
            idempotency_key=key,
            note=note[:500],
            created_at=datetime.now(timezone.utc),
        )
    )
    add_event(
        db,
        "task",
        task.id,
        "task.state_changed",
        f"Task {previous} → {target_state}: {task.title}",
    )
    db.flush()
    return task, True


def transition_history(rows: Iterable[TaskTransition]) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "task_id": row.task_id,
            "from_state": row.from_state,
            "to_state": row.to_state,
            "idempotency_key": row.idempotency_key,
            "note": row.note,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]

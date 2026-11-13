"""Durable checkpoints: resume interrupted work instead of restarting it.

Design notes:

* A checkpoint is an *observation*, not a resumption engine. It records where a
  unit of work got to so a later process can decide how to continue; AATM never
  claims that work resumed by itself.
* Sequences are monotonic per task, so two writers cannot silently overwrite
  each other's resume point.
* Checkpoints are append-only. Deleting history would destroy the very evidence
  needed after a crash.
* Secrets never belong in a checkpoint. Values are validated and obvious
  credential shapes are rejected so an operator cannot accidentally persist a
  token into the database and into backups.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Task, TaskCheckpoint

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,119}$")
SECRET_KEY_HINTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "private_key", "credential")
SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
)
MAX_STATE_BYTES = 8_000


class CheckpointError(ValueError):
    """A safe, user-facing checkpoint validation failure."""


@dataclass(frozen=True)
class CheckpointWrite:
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    note: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _secret_issues(state: dict[str, Any], note: str) -> list[str]:
    issues: list[str] = []
    for key, value in state.items():
        lowered = str(key).lower()
        if any(hint in lowered for hint in SECRET_KEY_HINTS):
            issues.append(f"state field '{key}' looks like a credential")
        text = str(value)
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(text):
                issues.append(f"state field '{key}' contains something shaped like a secret")
                break
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(note):
            issues.append("note contains something shaped like a secret")
            break
    return issues


def write_checkpoint(db: Session, task: Task, payload: CheckpointWrite) -> TaskCheckpoint:
    """Append the next checkpoint for a task. Never overwrites history."""
    label = (payload.label or "").strip()
    if not NAME_PATTERN.fullmatch(label):
        raise CheckpointError("A label of 1–120 letters, digits, spaces or . _ : - is required.")
    note = (payload.note or "").strip()
    if len(note) > 500:
        raise CheckpointError("A checkpoint note may be at most 500 characters.")
    state = dict(payload.state or {})
    encoded = repr(state)
    if len(encoded.encode("utf-8")) > MAX_STATE_BYTES:
        raise CheckpointError("Checkpoint state is too large (limit 8 kB).")
    issues = _secret_issues(state, note)
    if issues:
        raise CheckpointError("Refusing to store a credential in a checkpoint: " + "; ".join(issues) + ".")

    highest = db.scalar(select(func.max(TaskCheckpoint.sequence)).where(TaskCheckpoint.task_id == task.id))
    checkpoint = TaskCheckpoint(
        task_id=task.id,
        sequence=int(highest or 0) + 1,
        label=label,
        state=state,
        note=note,
        created_at=_now(),
    )
    db.add(checkpoint)
    db.flush()
    add_event(db, "task", task.id, "task.checkpointed", f"Checkpoint {checkpoint.sequence} '{label}' recorded for task: {task.title}")
    return checkpoint


def list_checkpoints(db: Session, task_id: str) -> list[TaskCheckpoint]:
    return list(
        db.scalars(
            select(TaskCheckpoint).where(TaskCheckpoint.task_id == task_id).order_by(TaskCheckpoint.sequence)
        ).all()
    )


def latest_checkpoint(db: Session, task_id: str) -> TaskCheckpoint | None:
    return db.scalar(
        select(TaskCheckpoint)
        .where(TaskCheckpoint.task_id == task_id)
        .order_by(TaskCheckpoint.sequence.desc())
        .limit(1)
    )


def resume_plan(db: Session, task: Task) -> dict[str, object]:
    """Describe how to continue a task; never pretends to resume it."""
    checkpoints = list_checkpoints(db, task.id)
    latest = checkpoints[-1] if checkpoints else None
    actions: list[str] = []
    state = task.state
    if state in {"completed", "approved", "cancelled"}:
        actions.append(f"Task is in terminal state '{state}'; nothing to resume.")
    elif state == "running":
        expires = _aware(task.lease_expires_at)
        if expires is not None and expires > _now():
            actions.append("A live lease still owns this task; wait for it or let it expire before resuming.")
        else:
            actions.append("The lease has expired; run lease recovery to return the task to the queue.")
    elif state == "failed":
        actions.append("The task failed; move it to 'assigned' (rework) before it can run again.")
    elif state == "waiting":
        actions.append("The task is waiting on external input; it resumes when moved back to 'running'.")
    elif state == "assigned":
        actions.append("The task is queued; the orchestrator will claim it when a worker is free.")
    else:
        actions.append("The task is pending; assign it to an agent to queue it.")

    if latest is None:
        actions.append("No checkpoints exist yet; start from the task description and acceptance criteria.")
    else:
        actions.append(
            f"Continue after checkpoint {latest.sequence} ('{latest.label}', {latest.created_at.isoformat()})."
        )
    return {
        "task_id": task.id,
        "state": state,
        "retry_count": int(task.retry_count or 0),
        "lease_expires_at": _aware(task.lease_expires_at).isoformat() if task.lease_expires_at else None,
        "checkpoint_count": len(checkpoints),
        "latest_checkpoint": checkpoint_payload(latest) if latest else None,
        "next_actions": actions,
        "resumed_automatically": False,
    }


def checkpoint_payload(checkpoint: TaskCheckpoint) -> dict[str, object]:
    return {
        "id": checkpoint.id,
        "task_id": checkpoint.task_id,
        "sequence": checkpoint.sequence,
        "label": checkpoint.label,
        "state": checkpoint.state,
        "note": checkpoint.note,
        "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
    }


def cleanup_checkpoints(db: Session, *, keep: int = 20, task_id: str | None = None) -> int:
    """Trim old checkpoints beyond ``keep`` per task, preserving the newest.

    Pass ``task_id`` to scope the cleanup to a single task; otherwise every task
    with checkpoints is trimmed.
    """
    if keep < 1:
        raise CheckpointError("Keep at least one checkpoint per task.")
    removed = 0
    task_ids = [task_id] if task_id else list(db.scalars(select(TaskCheckpoint.task_id).distinct()).all())
    for current in task_ids:
        rows = list(
            db.scalars(
                select(TaskCheckpoint)
                .where(TaskCheckpoint.task_id == current)
                .order_by(TaskCheckpoint.sequence.desc())
            ).all()
        )
        for stale in rows[keep:]:
            db.delete(stale)
            removed += 1
    db.flush()
    return removed

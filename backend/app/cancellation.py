"""Cooperative cancellation: a request the orchestrator actually honours.

Cancellation is a two-step protocol on purpose:

1. ``request_cancel`` records *intent* (`cancel_requested_at`, `cancel_reason`)
   and audits it. It does not touch the task's state, because an executor may
   still be mid-flight.
2. The executor/orchestrator calls ``honour_cancel`` at a safe boundary (before
   claiming, or between attempts). Only then does the task move to ``cancelled``
   through the validated workflow, which requires a reason.

A task that finished before the request arrived is **not** cancelled: the
outcome is recorded and the request is dropped, because rewriting a completed
result would be dishonest. ``honour_cancel`` reports that outcome.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Task
from app.workflow import WorkflowError, transition_task

CANCELLABLE_STATES = ("pending", "assigned", "running", "waiting", "reviewing", "failed", "rework_required")


class CancelError(ValueError):
    """A safe, user-facing cancellation failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def request_cancel(db: Session, task: Task, *, reason: str, requested_by: str = "local-user") -> Task:
    clean = (reason or "").strip()
    if not clean:
        raise CancelError("A cancellation request requires a reason.")
    if len(clean) > 500:
        raise CancelError("A cancellation reason may be at most 500 characters.")
    if task.state == "cancelled":
        raise CancelError("This task is already cancelled.")
    if task.state in ("completed", "approved"):
        raise CancelError(
            f"This task already reached '{task.state}'. Cancelling finished work would erase a recorded outcome."
        )
    if task.cancel_requested_at is not None:
        raise CancelError("A cancellation is already requested for this task.")
    task.cancel_requested_at = _now()
    task.cancel_reason = clean
    add_event(
        db,
        "task",
        task.id,
        "task.cancel_requested",
        f"Cancellation requested by {requested_by}: {clean[:300]}",
    )
    db.flush()
    return task


def withdraw_cancel(db: Session, task: Task) -> Task:
    if task.cancel_requested_at is None:
        raise CancelError("No cancellation is pending for this task.")
    task.cancel_requested_at = None
    task.cancel_reason = None
    add_event(db, "task", task.id, "task.cancel_withdrawn", "Cancellation request withdrawn.")
    db.flush()
    return task


def honour_cancel(db: Session, task: Task) -> dict[str, object]:
    """Apply a pending cancellation at a safe boundary. Returns what happened."""
    if task.cancel_requested_at is None:
        return {"cancelled": False, "reason": "no_pending_request"}
    if task.state in ("completed", "approved"):
        task.cancel_requested_at = None
        task.cancel_reason = None
        db.flush()
        return {"cancelled": False, "reason": "already_finished", "state": task.state}
    if task.state not in CANCELLABLE_STATES:
        return {"cancelled": False, "reason": "not_cancellable", "state": task.state}

    reason = task.cancel_reason or "cancellation requested"
    try:
        transition_task(
            db,
            task,
            target_state="cancelled",
            idempotency_key=f"cancel-{task.id}-{int(task.cancel_requested_at.timestamp())}",
            note=reason,
        )
    except WorkflowError as exc:
        raise CancelError(str(exc)) from exc
    task.lease_owner = None
    task.lease_expires_at = None
    task.next_attempt_at = None
    add_event(db, "task", task.id, "task.cancelled", f"Task cancelled at a safe boundary: {reason[:300]}")
    db.flush()
    return {"cancelled": True, "state": task.state, "reason": reason}


def pending_cancellations(db: Session) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.cancel_requested_at.is_not(None), Task.state.not_in(("cancelled", "completed", "approved")))
            .order_by(Task.cancel_requested_at)
        ).all()
    )


def honour_all(db: Session) -> dict[str, object]:
    """Apply every pending cancellation; used by the orchestrator and operators."""
    results = []
    for task in pending_cancellations(db):
        results.append({"task_id": task.id, **honour_cancel(db, task)})
    return {"applied": [item for item in results if item["cancelled"]], "skipped": [item for item in results if not item["cancelled"]]}

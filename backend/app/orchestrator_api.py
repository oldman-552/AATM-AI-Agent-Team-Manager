"""Observability and recovery endpoints for the durable orchestrator.

Deliberately absent: any endpoint that dispatches work to an executor. The
HTTP surface can inspect queue/lease state and recover expired leases, but it
cannot start a run, because the default executor refuses to execute and real
executors must be injected by authorized in-process code.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.models import Task
from app.orchestrator import DisabledExecutor, recover_expired_leases

router = APIRouter(prefix="/api/v1/orchestrator")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/status")
def orchestrator_status(db: Session = Depends(get_session)) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    tasks = list(db.scalars(select(Task)).all())
    running = [
        {
            "task_id": task.id,
            "title": task.title,
            "lease_owner": task.lease_owner,
            "lease_expires_at": _aware(task.lease_expires_at).isoformat() if task.lease_expires_at else None,
            "lease_expired": bool(_aware(task.lease_expires_at) and _aware(task.lease_expires_at) <= now),
        }
        for task in tasks
        if task.state == "running"
    ]
    waiting = [
        {
            "task_id": task.id,
            "title": task.title,
            "next_attempt_at": _aware(task.next_attempt_at).isoformat() if task.next_attempt_at else None,
        }
        for task in tasks
        if task.state == "assigned" and _aware(task.next_attempt_at) is not None
    ]
    return {
        "executor": {
            "configured": False,
            "name": type(DisabledExecutor()).__name__,
            "reason": DisabledExecutor.reason,
        },
        "counts": {
            "running": len(running),
            "waiting_for_retry": len(waiting),
            "expired_leases": sum(1 for item in running if item["lease_expired"]),
            "assigned": sum(1 for task in tasks if task.state == "assigned"),
            "failed": sum(1 for task in tasks if task.state == "failed"),
        },
        "leases": running,
        "retry_queue": waiting,
        "checked_at": now.isoformat(),
        "note": "Inspection and recovery only. The HTTP API cannot start a run, and no task is simulated.",
    }


@router.post("/recover")
def recover(db: Session = Depends(get_session)) -> dict[str, object]:
    """Return tasks with expired leases to the queue. Idempotent."""
    recovered = recover_expired_leases(db)
    db.commit()
    return {
        "recovered": recovered,
        "count": len(recovered),
        "note": "Expired leases were released and the interrupted attempts were recorded.",
    }

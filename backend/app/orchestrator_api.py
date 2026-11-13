"""Observability and recovery endpoints for the durable orchestrator.

The HTTP surface can inspect queue/lease state, recover expired leases, and —
**only when an operator has opted in with ``AATM_EXECUTION_ENABLED``** — start a
bounded run through the local process executor. An independent opt-in flag,
``AATM_ADAPTIVE_CONCURRENCY``, lets local resource telemetry reduce a run's
dispatch batch without raising the configured maximum. Both controls default
off; the run endpoint refuses with 409 while execution is disabled.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adaptive_concurrency import concurrency_policy
from app.api import get_session
from app.execution import (
    EXECUTION_FLAG,
    ExecutionError,
    LocalProcessExecutor,
    configured_programs,
    execution_enabled,
)
from app.models import Task
from app.orchestrator import DisabledExecutor, Orchestrator, OrchestratorConfig, recover_expired_leases

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
    enabled = execution_enabled()
    concurrency = concurrency_policy(db, in_flight=len(running))
    return {
        "executor": {
            "configured": enabled,
            "name": "LocalProcessExecutor" if enabled else type(DisabledExecutor()).__name__,
            "reason": (
                "Local commands run from each project's .aatm/exec.json, allow-listed and without a shell."
                if enabled
                else DisabledExecutor.reason
            ),
            "enabled_by": EXECUTION_FLAG if enabled else None,
            "allowed_programs": list(configured_programs()) if enabled else [],
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
        "concurrency": concurrency,
        "checked_at": now.isoformat(),
        "note": (
            "Execution is enabled by the operator; POST /run starts one bounded batch."
            if enabled
            else "Inspection and recovery only. The HTTP API cannot start a run, and no task is simulated."
        ),
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


@router.post("/run")
def run_batch(request: Request, db: Session = Depends(get_session)) -> dict[str, object]:
    """Start one bounded batch through the local executor.

    Refused unless ``AATM_EXECUTION_ENABLED`` is set: the whole point of the
    default is that nothing runs by accident, so this cannot be switched on by a
    request body or a query parameter.
    """
    if not execution_enabled():
        raise HTTPException(
            status_code=409,
            detail=(
                "Execution is disabled. Set AATM_EXECUTION_ENABLED=1 to allow the local "
                "process executor to start tasks."
            ),
        )

    run_lock = request.app.state.orchestrator_run_lock
    if not run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An orchestrator run is already active in this API process.")
    try:
        factory = request.app.state.session_factory
        executor = LocalProcessExecutor(factory, allowed_programs=configured_programs())
        concurrency = concurrency_policy(db, for_run=True)
        orchestrator = Orchestrator(
            executor=executor,
            config=OrchestratorConfig(max_concurrency=int(concurrency["effective_dispatch_budget"])),
        )
        try:
            report = orchestrator.run_once(db)
            db.commit()
        except ExecutionError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = report.as_dict()
        payload["concurrency"] = concurrency
        payload["note"] = (
            "Each task ran a named, allow-listed command from its project's .aatm/exec.json. "
            "Nothing was simulated; 'output' is real command output."
        )
        return payload
    finally:
        run_lock.release()

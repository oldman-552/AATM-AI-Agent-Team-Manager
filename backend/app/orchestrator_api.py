"""Observability and recovery endpoints for the durable orchestrator.

The HTTP surface can inspect queue/lease state, recover expired leases, and —
**only when an operator has opted in with ``AATM_EXECUTION_ENABLED``** — start a
bounded run through the local process executor. An independent opt-in flag,
``AATM_ADAPTIVE_CONCURRENCY``, lets local resource telemetry reduce a run's
dispatch batch without raising the configured maximum. Both controls default
off; the run endpoint refuses with 409 while execution is disabled.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adaptive_concurrency import concurrency_policy
from app.worker_slots import (
    MAX_WORKER_SLOTS,
    acquire_worker_slots,
    release_worker_slots,
    renew_worker_slots,
)
from app.dispatch_groups import (
    acquire_dispatch_group,
    release_dispatch_group,
    release_dispatch_groups,
    renew_dispatch_groups,
)
from app.api import get_session
from app.execution import (
    EXECUTION_FLAG,
    ExecutionError,
    LocalProcessExecutor,
    configured_programs,
    execution_enabled,
)
from app.models import Task
from app.orchestrator import LEASE_SECONDS, DisabledExecutor, Orchestrator, OrchestratorConfig, recover_expired_leases
from app.run_lock import acquire_run_lock, release_run_lock, renew_run_lock

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

    process_lock = request.app.state.orchestrator_run_lock
    if not process_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An orchestrator run is already active in this API process.")

    owner = f"api-run-{uuid4()}"
    lock_acquired = False
    try:
        lock_acquired = acquire_run_lock(db, owner, lease_seconds=LEASE_SECONDS)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="An orchestrator run is already active for this database.")

        factory = request.app.state.session_factory
        executor = LocalProcessExecutor(factory, allowed_programs=configured_programs())
        concurrency = concurrency_policy(db, for_run=True)
        requested_budget = max(0, int(concurrency["effective_dispatch_budget"]))
        worker_slot_ids = acquire_worker_slots(
            db,
            owner,
            limit=requested_budget,
            lease_seconds=LEASE_SECONDS,
            allowed_owner=owner,
        )
        if requested_budget > 0 and not worker_slot_ids:
            raise HTTPException(status_code=409, detail="No database-wide worker permits could be reserved for this run.")
        concurrency["requested_dispatch_budget"] = requested_budget
        concurrency["global_worker_slot_capacity"] = MAX_WORKER_SLOTS
        concurrency["global_worker_slots_acquired"] = len(worker_slot_ids)
        concurrency["effective_dispatch_budget"] = len(worker_slot_ids)
        owned_dispatch_groups: set[str] = set()

        def acquire_group(group_key: str) -> bool:
            acquired = acquire_dispatch_group(db, group_key, owner, lease_seconds=LEASE_SECONDS)
            if acquired:
                owned_dispatch_groups.add(group_key)
            return acquired

        def release_group(group_key: str) -> None:
            release_dispatch_group(db, group_key, owner)
            owned_dispatch_groups.discard(group_key)

        def renew_run_guard() -> None:
            if not renew_run_lock(db, owner, lease_seconds=LEASE_SECONDS):
                raise HTTPException(status_code=409, detail="The orchestrator database lock was lost during this run.")
            renewed_slots = renew_worker_slots(
                db, owner, lease_seconds=LEASE_SECONDS, allowed_owner=owner
            )
            if renewed_slots != len(worker_slot_ids):
                raise HTTPException(status_code=409, detail="A database-wide worker permit was lost during this run.")
            renewed_groups = renew_dispatch_groups(db, owner, lease_seconds=LEASE_SECONDS)
            if renewed_groups != len(owned_dispatch_groups):
                raise HTTPException(status_code=409, detail="A workspace dispatch-group lease was lost during this run.")

        orchestrator = Orchestrator(
            executor=executor,
            config=OrchestratorConfig(
                owner=owner,
                max_concurrency=int(concurrency["effective_dispatch_budget"]),
                heartbeat_callback=renew_run_guard,
                dispatch_group_acquire=acquire_group,
                dispatch_group_release=release_group,
            ),
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
        try:
            if lock_acquired:
                db.rollback()
                release_dispatch_groups(db, owner)
                release_worker_slots(db, owner)
                release_run_lock(db, owner)
        finally:
            process_lock.release()

"""Database-backed expiring permits for bounded cross-process task execution.

Each permit is one possible active task slot. Callers request at most the
configured database-wide cap, then retain the returned permits for the complete
lifetime of their worker batch. The API run endpoint reserves these permits
before dispatch and retains them for the batch. Worker-permit reservation and
renewal share the singleton gate with exclusive workspace mutations.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import OrchestratorRunLock, OrchestratorWorkerSlot
from app.run_lock import LOCK_ID

MAX_WORKER_SLOTS = 20


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _lock_dispatch_gate(db: Session, current: datetime, *, allowed_owner: str | None = None) -> bool:
    """Take the shared gate, optionally for the run already owning it.

    A dispatcher may reserve a group while it owns the global run lock; an
    unrelated reservation is blocked by an exclusive workspace mutation.
    """
    result = db.execute(
        update(OrchestratorRunLock)
        .where(
            OrchestratorRunLock.id == LOCK_ID,
            or_(
                OrchestratorRunLock.owner.is_(None),
                OrchestratorRunLock.expires_at.is_(None),
                OrchestratorRunLock.expires_at <= current,
                *(
                    [
                        and_(
                            OrchestratorRunLock.owner == allowed_owner,
                            OrchestratorRunLock.expires_at > current,
                        )
                    ]
                    if allowed_owner is not None
                    else []
                ),
            ),
        )
        .values(expires_at=OrchestratorRunLock.expires_at)
    )
    return result.rowcount == 1


def acquire_worker_slots(
    db: Session,
    owner: str,
    *,
    limit: int,
    lease_seconds: int,
    now: datetime | None = None,
    allowed_owner: str | None = None,
) -> list[int]:
    """Lease available slots in ``1..limit`` to this run, atomically per slot.

    All API processes sharing the database must use the same configured limit.
    Conditional updates make simultaneous acquisitions compete at the database
    rather than relying on a process-local semaphore. Expired permits can be
    reclaimed after a process crash. The caller may receive fewer than
    ``limit`` slots when other runs currently own permits.
    """
    normalized_limit = max(0, min(int(limit), MAX_WORKER_SLOTS))
    if not owner or len(owner) > 120:
        raise ValueError("Worker-slot owner must contain 1–120 characters.")
    if normalized_limit == 0:
        return []

    current = _now(now)
    expires = current + timedelta(seconds=max(1, lease_seconds))
    acquired: list[int] = []
    try:
        # Serialize permit reservation against exclusive workspace mutations.
        # This conditional no-op update holds the shared gate row through the
        # permit writes and commit. A mutation holding the gate makes the CAS
        # fail; a mutation arriving afterward will observe our live permits.
        if not _lock_dispatch_gate(db, current, allowed_owner=allowed_owner):
            db.rollback()
            return []

        for slot_id in range(1, normalized_limit + 1):
            result = db.execute(
                update(OrchestratorWorkerSlot)
                .where(
                    OrchestratorWorkerSlot.id == slot_id,
                    or_(
                        OrchestratorWorkerSlot.owner.is_(None),
                        OrchestratorWorkerSlot.expires_at.is_(None),
                        OrchestratorWorkerSlot.expires_at <= current,
                    ),
                )
                .values(owner=owner, expires_at=expires)
            )
            if result.rowcount == 1:
                acquired.append(slot_id)
        db.commit()
        return acquired
    except Exception:
        db.rollback()
        raise


def renew_worker_slots(
    db: Session,
    owner: str,
    *,
    lease_seconds: int,
    now: datetime | None = None,
    allowed_owner: str | None = None,
) -> int:
    """Renew only permits still held by ``owner``; return the count renewed."""
    current = _now(now)
    try:
        if not _lock_dispatch_gate(db, current, allowed_owner=allowed_owner):
            db.rollback()
            return 0
        result = db.execute(
            update(OrchestratorWorkerSlot)
            .where(
                OrchestratorWorkerSlot.owner == owner,
                OrchestratorWorkerSlot.expires_at > current,
            )
            .values(expires_at=current + timedelta(seconds=max(1, lease_seconds)))
        )
        renewed = int(result.rowcount or 0)
        db.commit()
        return renewed
    except Exception:
        db.rollback()
        raise


def release_worker_slots(db: Session, owner: str) -> int:
    """Release all permits held by ``owner`` without disturbing other runs."""
    try:
        result = db.execute(
            update(OrchestratorWorkerSlot)
            .where(OrchestratorWorkerSlot.owner == owner)
            .values(owner=None, expires_at=None)
        )
        released = int(result.rowcount or 0)
        db.commit()
        return released
    except Exception:
        db.rollback()
        raise


def active_worker_slots(db: Session, *, now: datetime | None = None) -> list[OrchestratorWorkerSlot]:
    """Return currently live permits in deterministic slot order."""
    current = _now(now)
    return list(
        db.scalars(
            select(OrchestratorWorkerSlot)
            .where(
                OrchestratorWorkerSlot.owner.is_not(None),
                OrchestratorWorkerSlot.expires_at > current,
            )
            .order_by(OrchestratorWorkerSlot.id)
        ).all()
    )

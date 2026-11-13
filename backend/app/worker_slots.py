"""Database-backed expiring permits for bounded cross-process task execution.

Each permit is one possible active task slot. Callers request at most the
configured database-wide cap, then retain the returned permits for the complete
lifetime of their worker batch. The current API still uses the singleton run
lock; these primitives are groundwork and are not yet wired into dispatch.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import OrchestratorWorkerSlot

MAX_WORKER_SLOTS = 20


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def acquire_worker_slots(
    db: Session,
    owner: str,
    *,
    limit: int,
    lease_seconds: int,
    now: datetime | None = None,
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
) -> int:
    """Renew only permits still held by ``owner``; return the count renewed."""
    current = _now(now)
    try:
        result = db.execute(
            update(OrchestratorWorkerSlot)
            .where(OrchestratorWorkerSlot.owner == owner)
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

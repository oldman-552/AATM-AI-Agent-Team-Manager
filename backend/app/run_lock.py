"""Database-backed gate for orchestrator runs and workspace mutations.

The migration-seeded singleton row serializes API run requests (for now) and
acts as an exclusive workspace-mutation gate. Worker-permit acquisition and
renewal lock this same row, so a mutation cannot overlap a live permit and a
new worker batch cannot begin during a mutation. The lease expires if the
exclusive owner process dies and is renewed by an active orchestrator run.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models import OrchestratorRunLock, OrchestratorWorkerSlot

LOCK_ID = "global"


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def acquire_run_lock(db: Session, owner: str, *, lease_seconds: int, now: datetime | None = None) -> bool:
    """Acquire the exclusive workspace-mutation gate if it is safe to do so.

    The singleton row also serializes each worker-permit acquisition. Holding
    its write lock while checking active permits ensures a mutation cannot win
    a time-of-check/time-of-use race against a new worker batch.
    """
    current = _now(now)
    try:
        result = db.execute(
            update(OrchestratorRunLock)
            .where(
                OrchestratorRunLock.id == LOCK_ID,
                or_(OrchestratorRunLock.owner.is_(None), OrchestratorRunLock.expires_at.is_(None), OrchestratorRunLock.expires_at <= current),
            )
            .values(owner=owner, expires_at=current + timedelta(seconds=max(1, lease_seconds)))
        )
        acquired = result.rowcount == 1
        if acquired:
            active_permits = db.scalar(
                select(func.count())
                .select_from(OrchestratorWorkerSlot)
                .where(
                    OrchestratorWorkerSlot.owner.is_not(None),
                    OrchestratorWorkerSlot.expires_at > current,
                )
            ) or 0
            if active_permits:
                db.rollback()
                return False
        db.commit()
        return acquired
    except Exception:
        db.rollback()
        raise


def renew_run_lock(db: Session, owner: str, *, lease_seconds: int, now: datetime | None = None) -> bool:
    """Renew this owner's lock; returns false if another process took it."""
    current = _now(now)
    try:
        result = db.execute(
            update(OrchestratorRunLock)
            .where(OrchestratorRunLock.id == LOCK_ID, OrchestratorRunLock.owner == owner)
            .values(expires_at=current + timedelta(seconds=max(1, lease_seconds)))
        )
        renewed = result.rowcount == 1
        db.commit()
        return renewed
    except Exception:
        db.rollback()
        raise


def release_run_lock(db: Session, owner: str) -> bool:
    """Release only if the caller still owns the singleton lock."""
    try:
        result = db.execute(
            update(OrchestratorRunLock)
            .where(OrchestratorRunLock.id == LOCK_ID, OrchestratorRunLock.owner == owner)
            .values(owner=None, expires_at=None)
        )
        released = result.rowcount == 1
        db.commit()
        return released
    except Exception:
        db.rollback()
        raise

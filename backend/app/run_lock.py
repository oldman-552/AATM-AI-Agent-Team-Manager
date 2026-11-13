"""Database-backed singleton lease for orchestrator API runs.

The lock is an atomic conditional UPDATE against a migration-seeded singleton
row, so separate API processes sharing the same database cannot start runs at
the same time. The lock expires if a process dies and is renewed by the
orchestrator while task executors are active.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models import OrchestratorRunLock

LOCK_ID = "global"


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def acquire_run_lock(db: Session, owner: str, *, lease_seconds: int, now: datetime | None = None) -> bool:
    """Acquire the singleton run lock if it is free or expired."""
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

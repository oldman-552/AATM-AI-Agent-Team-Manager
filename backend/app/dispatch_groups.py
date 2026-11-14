"""Database-backed leases for tasks that share a mutable project workspace."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import OrchestratorDispatchGroupLease
from app.worker_slots import _lock_dispatch_gate


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def acquire_dispatch_group(
    db: Session,
    group_key: str,
    owner: str,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Acquire a workspace dispatch-group lease, serialized with mutations."""
    key = group_key.strip()
    if not key or len(key) > 200:
        raise ValueError("Dispatch-group key must contain 1–200 characters.")
    if not owner or len(owner) > 120:
        raise ValueError("Dispatch-group owner must contain 1–120 characters.")
    current = _now(now)
    expires = current + timedelta(seconds=max(1, lease_seconds))
    try:
        # API run owners can reserve groups while holding the singleton run
        # lock. All other owners are excluded by an active mutation lock.
        if not _lock_dispatch_gate(db, current, allowed_owner=owner):
            db.rollback()
            return False
        row = db.get(OrchestratorDispatchGroupLease, key)
        if row is None:
            db.add(OrchestratorDispatchGroupLease(group_key=key, owner=owner, expires_at=expires))
            db.commit()
            return True

        result = db.execute(
            update(OrchestratorDispatchGroupLease)
            .where(
                OrchestratorDispatchGroupLease.group_key == key,
                or_(
                    OrchestratorDispatchGroupLease.owner.is_(None),
                    OrchestratorDispatchGroupLease.expires_at.is_(None),
                    OrchestratorDispatchGroupLease.expires_at <= current,
                    OrchestratorDispatchGroupLease.owner == owner,
                ),
            )
            .values(owner=owner, expires_at=expires)
            .execution_options(synchronize_session=False)
        )
        acquired = result.rowcount == 1
        db.commit()
        return acquired
    except Exception:
        db.rollback()
        raise


def renew_dispatch_groups(
    db: Session,
    owner: str,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> int:
    """Renew all still-owned groups; group reservation shares the mutation gate."""
    current = _now(now)
    try:
        if not _lock_dispatch_gate(db, current, allowed_owner=owner):
            db.rollback()
            return 0
        result = db.execute(
            update(OrchestratorDispatchGroupLease)
            .where(
                OrchestratorDispatchGroupLease.owner == owner,
                OrchestratorDispatchGroupLease.expires_at > current,
            )
            .values(expires_at=current + timedelta(seconds=max(1, lease_seconds)))
        )
        renewed = int(result.rowcount or 0)
        db.commit()
        return renewed
    except Exception:
        db.rollback()
        raise


def release_dispatch_group(db: Session, group_key: str, owner: str) -> bool:
    """Release one group only when the caller still owns it."""
    try:
        result = db.execute(
            update(OrchestratorDispatchGroupLease)
            .where(
                OrchestratorDispatchGroupLease.group_key == group_key,
                OrchestratorDispatchGroupLease.owner == owner,
            )
            .values(owner=None, expires_at=None)
        )
        released = result.rowcount == 1
        db.commit()
        return released
    except Exception:
        db.rollback()
        raise


def release_dispatch_groups(db: Session, owner: str) -> int:
    """Release all group leases owned by a run during normal or failed cleanup."""
    try:
        result = db.execute(
            update(OrchestratorDispatchGroupLease)
            .where(OrchestratorDispatchGroupLease.owner == owner)
            .values(owner=None, expires_at=None)
        )
        released = int(result.rowcount or 0)
        db.commit()
        return released
    except Exception:
        db.rollback()
        raise


def active_dispatch_groups(
    db: Session,
    *,
    now: datetime | None = None,
) -> list[OrchestratorDispatchGroupLease]:
    current = _now(now)
    return list(
        db.scalars(
            select(OrchestratorDispatchGroupLease)
            .where(
                OrchestratorDispatchGroupLease.owner.is_not(None),
                OrchestratorDispatchGroupLease.expires_at > current,
            )
            .order_by(OrchestratorDispatchGroupLease.group_key)
        ).all()
    )

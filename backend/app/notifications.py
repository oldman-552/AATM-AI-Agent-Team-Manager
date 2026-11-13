"""In-app notifications derived from real pending work.

A notification is **not** an invented message stream. Each one is derived from a
row that genuinely needs attention:

* a pending approval request,
* a task in `failed` or `rework_required`,
* a task whose lease expired and is waiting for recovery.

Read state is persisted (`notification_reads`) so "seen" survives a restart,
instead of a client-side flag that resets. Messages are built from translatable
keys plus structured data, so the UI renders them in the user's language rather
than the server hardcoding English.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import ApprovalRequest, NotificationRead, Task

MAX_NOTIFICATIONS = 100


class NotificationError(ValueError):
    """A safe, user-facing notification failure."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _key(prefix: str, row_id: str) -> str:
    return f"{prefix}:{row_id}"


def collect(db: Session) -> list[dict[str, object]]:
    """Build the notification list from live rows, newest first."""
    items: list[dict[str, object]] = []

    approvals = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.requested_at.desc())
        .limit(MAX_NOTIFICATIONS)
    ).all()
    for approval in approvals:
        items.append(
            {
                "id": _key("approval", approval.id),
                "kind": "approval_pending",
                "entity_type": approval.entity_type,
                "entity_id": approval.entity_id,
                "message_key": "notificationApprovalPending",
                "data": {"kind": approval.kind, "summary": approval.summary},
                "action_view": "approvals",
                "severity": "attention",
                "created_at": _aware(approval.requested_at).isoformat() if approval.requested_at else None,
            }
        )

    stuck = db.scalars(
        select(Task)
        .where(Task.state.in_(("failed", "rework_required")))
        .order_by(Task.updated_at.desc())
        .limit(MAX_NOTIFICATIONS)
    ).all()
    for task in stuck:
        items.append(
            {
                "id": _key("task", task.id),
                "kind": "task_needs_attention",
                "entity_type": "task",
                "entity_id": task.id,
                "message_key": "notificationTaskFailing" if task.state == "failed" else "notificationTaskRework",
                "data": {"title": task.title, "state": task.state, "retry_count": task.retry_count},
                "action_view": "tasks",
                "severity": "warning" if task.state == "rework_required" else "error",
                "created_at": _aware(task.updated_at).isoformat() if task.updated_at else None,
            }
        )

    expired = db.scalars(
        select(Task)
        .where(
            Task.state == "running",
            Task.lease_expires_at.is_not(None),
            Task.lease_expires_at < datetime.now(timezone.utc),
        )
        .order_by(Task.lease_expires_at)
        .limit(MAX_NOTIFICATIONS)
    ).all()
    for task in expired:
        items.append(
            {
                "id": _key("lease", task.id),
                "kind": "lease_expired",
                "entity_type": "task",
                "entity_id": task.id,
                "message_key": "notificationLeaseExpired",
                "data": {"title": task.title, "owner": task.lease_owner},
                "action_view": "tasks",
                "severity": "attention",
                "created_at": _aware(task.lease_expires_at).isoformat() if task.lease_expires_at else None,
            }
        )

    reads = {
        row.notification_id: _aware(row.read_at)
        for row in db.scalars(select(NotificationRead)).all()
    }
    for item in items:
        item["read"] = item["id"] in reads
        item["read_at"] = reads[item["id"]].isoformat() if reads.get(item["id"]) else None

    items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return items[:MAX_NOTIFICATIONS]


def summary(db: Session) -> dict[str, object]:
    items = collect(db)
    unread = [item for item in items if not item["read"]]
    return {
        "notifications": items,
        "unread": len(unread),
        "total": len(items),
        "source": "Derived from pending approvals, failed/rework tasks and expired leases; no synthetic events.",
    }


def mark_read(db: Session, notification_ids: list[str]) -> int:
    """Persist read state for the given derived ids."""
    existing = {
        row.notification_id
        for row in db.scalars(
            select(NotificationRead).where(NotificationRead.notification_id.in_(notification_ids))
        ).all()
    }
    created = 0
    now = datetime.now(timezone.utc)
    for notification_id in notification_ids:
        if not notification_id or len(notification_id) > 80 or ":" not in notification_id:
            raise NotificationError("Notification ids look like '<kind>:<uuid>'.")
        if notification_id in existing:
            continue
        db.add(NotificationRead(notification_id=notification_id, read_at=now))
        created += 1
    db.flush()
    return created


def mark_all_read(db: Session) -> dict[str, object]:
    ids = [str(item["id"]) for item in collect(db) if not item["read"]]
    created = mark_read(db, ids) if ids else 0
    add_event(db, "notification", None, "notification.all_read", f"{created} notification(s) marked read.")
    db.flush()
    return {"marked_read": created}


def unread_count(db: Session) -> int:
    return len([item for item in collect(db) if not item["read"]])


def prune_reads(db: Session, *, older_than_days: int = 90) -> int:
    """Keep the read-state table small; notifications themselves are derived."""
    if older_than_days < 1:
        raise NotificationError("Retention must be at least one day.")
    cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
    removed = 0
    for row in db.scalars(select(NotificationRead)).all():
        read_at = _aware(row.read_at)
        if read_at is not None and read_at.timestamp() < cutoff:
            db.delete(row)
            removed += 1
    db.flush()
    return removed

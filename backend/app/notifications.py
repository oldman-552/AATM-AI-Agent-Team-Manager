"""In-app notifications derived from real pending work.

A notification is **not** an invented message stream. Each one is derived from a
row that genuinely needs attention:

* a pending approval request,
* a task in `failed` or `rework_required`,
* a task whose lease expired and is waiting for recovery, and
* persisted estimated/confirmed usage at or above 80% of an applicable budget.

Budget notifications are advisory only. The provider `BudgetGuard` remains the
sole enforcement point and continues to deny only when the requested estimate
would exceed an applicable hard limit.

Read state is persisted (`notification_reads`) so "seen" survives a restart,
instead of a client-side flag that resets. Messages are built from translatable
keys plus structured data, so the UI renders them in the user's language rather
than the server hardcoding English.
"""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import ApprovalRequest, NotificationRead, Task, UsageRecord
from app.provider_store import load_limits

MAX_NOTIFICATIONS = 100


class NotificationError(ValueError):
    """A safe, user-facing notification failure."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _key(prefix: str, row_id: str) -> str:
    return f"{prefix}:{row_id}"


BUDGET_ALERT_THRESHOLD = 0.80


def _budget_notifications(db: Session) -> list[dict[str, object]]:
    """Derive advisory near-limit alerts from persisted usage; never enforce a limit here."""
    limits = load_limits(db)
    if not limits:
        return []

    records = list(db.scalars(select(UsageRecord).order_by(UsageRecord.created_at.desc())).all())
    now = datetime.now(timezone.utc)
    alerts: list[dict[str, object]] = []

    for limit in limits:
        if limit.limit_usd <= 0:
            continue
        providers = sorted(
            {row.provider_id for row in records if limit.provider_id in {"*", row.provider_id}}
        )
        for provider_id in providers:
            provider_records = [row for row in records if row.provider_id == provider_id]
            if limit.scope in {"daily", "monthly"}:
                if limit.scope == "daily":
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    period = start.date().isoformat()
                else:
                    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    period = start.strftime("%Y-%m")
                scoped_records = [row for row in provider_records if _aware(row.created_at) >= start]
                groups = [("", scoped_records)]
            elif limit.scope == "agent":
                if limit.scope_key:
                    groups = [(limit.scope_key, [row for row in provider_records if row.agent_id == limit.scope_key])]
                else:
                    keys = sorted({row.agent_id for row in provider_records if row.agent_id})
                    groups = [(key, [row for row in provider_records if row.agent_id == key]) for key in keys]
                period = "all-time"
            elif limit.scope == "project":
                if limit.scope_key:
                    groups = [(limit.scope_key, [row for row in provider_records if row.project_id == limit.scope_key])]
                else:
                    keys = sorted({row.project_id for row in provider_records if row.project_id})
                    groups = [(key, [row for row in provider_records if row.project_id == key]) for key in keys]
                period = "all-time"
            elif limit.scope == "credential":
                if limit.scope_key:
                    groups = [(limit.scope_key, [row for row in provider_records if row.credential_ref == limit.scope_key])]
                else:
                    keys = sorted({row.credential_ref for row in provider_records if row.credential_ref})
                    groups = [(key, [row for row in provider_records if row.credential_ref == key]) for key in keys]
                period = "all-time"
            else:  # global
                groups = [("", provider_records)]
                period = "all-time"

            for scope_key, matching in groups:
                if not matching:
                    continue
                used = round(
                    sum(
                        float(row.confirmed_cost_usd)
                        if row.billing_status == "confirmed" and row.confirmed_cost_usd is not None
                        else float(row.estimated_cost_usd)
                        for row in matching
                    ),
                    6,
                )
                ratio = used / float(limit.limit_usd)
                if ratio < BUDGET_ALERT_THRESHOLD:
                    continue

                identity = {
                    "provider": provider_id,
                    "scope": limit.scope,
                    "scope_key": scope_key,
                    "period": period,
                    "limit": round(float(limit.limit_usd), 6),
                }
                digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]
                confirmed_flags = [
                    row.billing_status == "confirmed" and row.confirmed_cost_usd is not None
                    for row in matching
                ]
                billing = "confirmed" if all(confirmed_flags) else "estimated" if not any(confirmed_flags) else "mixed"
                scope_label = limit.scope
                if limit.scope in {"agent", "project"} and scope_key:
                    scope_label = f"{limit.scope} {scope_key[:8]}"
                elif limit.scope == "credential":
                    scope_label = "credential"
                latest = max((_aware(row.created_at) for row in matching if row.created_at), default=now)
                alerts.append(
                    {
                        "id": f"budget:{digest}",
                        "kind": "budget_near_limit",
                        "entity_type": "provider_budget",
                        "entity_id": None,
                        "message_key": "notificationBudgetNearLimit",
                        "data": {
                            "provider": provider_id,
                            "scope": limit.scope,
                            "scope_label": scope_label,
                            "used_usd": round(used, 2),
                            "limit_usd": round(float(limit.limit_usd), 2),
                            "percent": min(999, round(ratio * 100)),
                            "billing_basis": billing,
                        },
                        "action_view": "providers",
                        "severity": "warning" if ratio < 1 else "error",
                        "created_at": latest.isoformat(),
                    }
                )
    return alerts


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

    items.extend(_budget_notifications(db))

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
        "source": "Derived from pending approvals, failed/rework tasks, expired leases, and persisted usage at or above 80% of a budget; no synthetic events.",
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
            raise NotificationError("Notification ids must look like '<kind>:<identifier>'.")
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

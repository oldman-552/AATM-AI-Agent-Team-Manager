"""Observable execution timeline, assembled from persisted history.

Nothing here is invented. Each entry corresponds to a row that exists:

* ``task_transitions`` — every state change with its note and idempotency key,
* ``task_checkpoints`` — resumable milestones,
* ``audit_events`` — lease recovery, assignments, plan application, review,
* ``review_records`` / ``approval_requests`` — verdicts and gates.

The timeline is therefore a *projection*: it cannot claim work happened that the
database does not record. Entries are sorted by timestamp with a stable
tiebreaker, and each carries its `source` so a reader can audit the claim.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalRequest, AuditEvent, ReviewRecord, Task, TaskCheckpoint, TaskTransition

MAX_ENTRIES = 500


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


def task_timeline(db: Session, task: Task, *, limit: int = MAX_ENTRIES) -> dict[str, object]:
    entries: list[dict[str, object]] = []

    for row in db.scalars(
        select(TaskTransition).where(TaskTransition.task_id == task.id).order_by(TaskTransition.created_at)
    ).all():
        entries.append(
            {
                "at": _iso(row.created_at),
                "kind": "transition",
                "title_key": "timelineTransition",
                "data": {"from": row.from_state, "to": row.to_state},
                "detail": row.note,
                "reference": row.idempotency_key,
                "source": "task_transitions",
            }
        )

    for checkpoint in db.scalars(
        select(TaskCheckpoint).where(TaskCheckpoint.task_id == task.id).order_by(TaskCheckpoint.created_at)
    ).all():
        entries.append(
            {
                "at": _iso(checkpoint.created_at),
                "kind": "checkpoint",
                "title_key": "timelineCheckpoint",
                "data": {"sequence": checkpoint.sequence, "label": checkpoint.label},
                "detail": checkpoint.note,
                "reference": checkpoint.id,
                "source": "task_checkpoints",
            }
        )

    for event in db.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == "task", AuditEvent.entity_id == task.id)
    ).all():
        entries.append(
            {
                "at": _iso(event.created_at),
                "kind": "audit",
                "title_key": "timelineAudit",
                "data": {"event_type": event.event_type},
                "detail": event.summary,
                "reference": event.id,
                "source": "audit_events",
            }
        )

    for review in db.scalars(select(ReviewRecord).where(ReviewRecord.task_id == task.id)).all():
        entries.append(
            {
                "at": _iso(review.created_at),
                "kind": "review",
                "title_key": "timelineReview",
                "data": {"verdict": review.verdict, "checks": len(review.checks or [])},
                "detail": review.summary,
                "reference": review.id,
                "source": "review_records",
            }
        )

    for approval in db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.entity_type == "task", ApprovalRequest.entity_id == task.id
        )
    ).all():
        entries.append(
            {
                "at": _iso(approval.requested_at),
                "kind": "approval_requested",
                "title_key": "timelineApprovalRequested",
                "data": {"approval_kind": approval.kind, "status": approval.status},
                "detail": approval.summary,
                "reference": approval.id,
                "source": "approval_requests",
            }
        )
        if approval.decided_at is not None:
            entries.append(
                {
                    "at": _iso(approval.decided_at),
                    "kind": f"approval_{approval.status}",
                    "title_key": "timelineApprovalDecided",
                    "data": {"approval_kind": approval.kind, "decided_by": approval.decided_by},
                    "detail": approval.decision_note,
                    "reference": approval.id,
                    "source": "approval_requests",
                }
            )

    entries.sort(key=lambda item: (item["at"] or "", str(item["kind"]), str(item["reference"])))
    trimmed = entries[:limit]
    return {
        "task_id": task.id,
        "task_title": task.title,
        "state": task.state,
        "entries": trimmed,
        "total": len(entries),
        "truncated": len(entries) > len(trimmed),
        "sources": sorted({str(item["source"]) for item in trimmed}),
        "note": "Assembled from stored rows only; an action that was not recorded cannot appear here.",
    }


def project_timeline(db: Session, project_id: str, *, limit: int = 100) -> dict[str, object]:
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    entries: list[dict[str, object]] = []
    for task in tasks:
        for item in task_timeline(db, task, limit=limit)["entries"]:  # type: ignore[index]
            entries.append({**item, "task_id": task.id, "task_title": task.title})
    entries.sort(key=lambda item: (item["at"] or "", str(item["task_id"]), str(item["kind"])), reverse=True)
    trimmed = entries[:limit]
    return {
        "project_id": project_id,
        "tasks": len(tasks),
        "entries": trimmed,
        "total": len(entries),
        "truncated": len(entries) > len(trimmed),
        "note": "Newest first across every task in the project, from stored rows only.",
    }

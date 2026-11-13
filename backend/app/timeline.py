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
    """Newest-first across a project, assembled with one query per table.

    Calling ``task_timeline`` per task would issue five queries per row; this
    reads each table once for the whole project instead, so a large project
    stays fast. The entry shape is identical to the single-task timeline.
    """
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    if not tasks:
        return {
            "project_id": project_id,
            "tasks": 0,
            "entries": [],
            "total": 0,
            "truncated": False,
            "sources": [],
            "note": "Newest first across every task in the project, from stored rows only.",
        }
    titles = {task.id: task.title for task in tasks}
    task_ids = list(titles)

    # Fetch every row this project needs, then map them in memory, so the number
    # of statements is constant rather than proportional to the task count.
    transitions = list(
        db.scalars(select(TaskTransition).where(TaskTransition.task_id.in_(task_ids))).all()
    )
    checkpoints = list(
        db.scalars(select(TaskCheckpoint).where(TaskCheckpoint.task_id.in_(task_ids))).all()
    )
    events = list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.entity_type == "task", AuditEvent.entity_id.in_(task_ids))
        ).all()
    )
    reviews = list(
        db.scalars(select(ReviewRecord).where(ReviewRecord.task_id.in_(task_ids))).all()
    )
    approvals = list(
        db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.entity_type == "task", ApprovalRequest.entity_id.in_(task_ids)
            )
        ).all()
    )

    def row(entry: dict[str, object], task_id: str) -> dict[str, object]:
        return {**entry, "task_id": task_id, "task_title": titles[task_id]}

    entries: list[dict[str, object]] = []
    for item in transitions:
        entries.append(row({
            "at": _iso(item.created_at), "kind": "transition", "title_key": "timelineTransition",
            "data": {"from": item.from_state, "to": item.to_state}, "detail": item.note,
            "reference": item.idempotency_key, "source": "task_transitions",
        }, item.task_id))
    for item in checkpoints:
        entries.append(row({
            "at": _iso(item.created_at), "kind": "checkpoint", "title_key": "timelineCheckpoint",
            "data": {"sequence": item.sequence, "label": item.label}, "detail": item.note,
            "reference": item.id, "source": "task_checkpoints",
        }, item.task_id))
    for item in events:
        entries.append(row({
            "at": _iso(item.created_at), "kind": "audit", "title_key": "timelineAudit",
            "data": {"event_type": item.event_type}, "detail": item.summary,
            "reference": item.id, "source": "audit_events",
        }, item.entity_id))
    for item in reviews:
        entries.append(row({
            "at": _iso(item.created_at), "kind": f"review_{item.verdict}", "title_key": "timelineReviewDecided",
            "data": {"verdict": item.verdict, "reviewer_agent_id": item.reviewer_agent_id},
            "detail": item.summary, "reference": item.id, "source": "review_records",
        }, item.task_id))
    for item in approvals:
        task_id = item.entity_id  # approvals are linked by (entity_type, entity_id)
        if task_id not in titles:
            continue
        entries.append(row({
            "at": _iso(item.requested_at), "kind": "approval_requested",
            "title_key": "timelineApprovalRequested",
            "data": {"approval_kind": item.kind, "status": item.status}, "detail": item.summary,
            "reference": item.id, "source": "approval_requests",
        }, task_id))
        if item.decided_at is not None:
            entries.append(row({
                "at": _iso(item.decided_at), "kind": f"approval_{item.status}",
                "title_key": "timelineApprovalDecided",
                "data": {"approval_kind": item.kind, "decided_by": item.decided_by},
                "detail": item.decision_note, "reference": item.id, "source": "approval_requests",
            }, task_id))

    entries.sort(key=lambda item: (item["at"] or "", str(item["task_id"]), str(item["kind"])), reverse=True)
    trimmed = entries[:limit]
    sources = sorted({str(entry["source"]) for entry in entries})
    return {
        "project_id": project_id,
        "tasks": len(tasks),
        "entries": trimmed,
        "total": len(entries),
        "truncated": len(entries) > len(trimmed),
        "sources": sources,
        "note": "Newest first across every task in the project, from stored rows only.",
    }

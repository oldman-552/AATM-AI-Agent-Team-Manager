"""Evidence-based analytics computed only from persisted records.

Every number here is derived from rows that exist: tasks, transitions, review
records, approvals, checkpoints and audit events. There are no synthetic scores,
no "productivity indices" and no estimates presented as measurements.

Deliberate omissions:

* No provider cost analytic — usage is only recorded for gated, consented
  requests, and there is no live traffic to summarize.
* No per-agent quality score — verdicts are sparse; a score would imply
  statistical confidence that does not exist.
* Cycle time is reported only for tasks that reached a terminal state, and the
  sample size is always returned alongside it so a single task cannot be
  mistaken for a trend.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    ApprovalRequest,
    AuditEvent,
    Project,
    ReviewRecord,
    Task,
    TaskCheckpoint,
    TaskTransition,
)

TERMINAL_STATES = ("completed", "approved", "cancelled")
ACTIVE_STATES = ("assigned", "running", "waiting")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def throughput(db: Session, *, days: int = 14, now: datetime | None = None) -> dict[str, object]:
    """Transitions into a terminal state, bucketed per UTC day."""
    current = now or datetime.now(timezone.utc)
    start = (current - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(TaskTransition.created_at, TaskTransition.to_state).where(
            TaskTransition.created_at >= start,
            TaskTransition.to_state.in_(TERMINAL_STATES),
        )
    ).all()
    buckets: dict[str, dict[str, int]] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        buckets[day] = {"completed": 0, "approved": 0, "cancelled": 0}
    for created_at, to_state in rows:
        stamp = _aware(created_at)
        if stamp is None:
            continue
        key = stamp.date().isoformat()
        if key in buckets and str(to_state) in buckets[key]:
            buckets[key][str(to_state)] += 1
    return {
        "days": days,
        "start": start.date().isoformat(),
        "buckets": [{"date": day, **counts} for day, counts in buckets.items()],
        "total": len(rows),
        "source": "task_transitions rows entering completed/approved/cancelled",
    }


def cycle_time(db: Session, *, limit: int = 200) -> dict[str, object]:
    """Wall-clock time from task creation to its first terminal transition.

    Only tasks with a recorded terminal transition are included; the sample size
    is returned so the reader can judge how much the average means.
    """
    terminal = db.execute(
        select(TaskTransition.task_id, func.min(TaskTransition.created_at))
        .where(TaskTransition.to_state.in_(TERMINAL_STATES))
        .group_by(TaskTransition.task_id)
        .limit(limit)
    ).all()
    if not terminal:
        return {"samples": 0, "average_seconds": None, "median_seconds": None, "max_seconds": None}
    task_ids = [row[0] for row in terminal]
    finished_at = {row[0]: _aware(row[1]) for row in terminal}
    created_rows = db.execute(select(Task.id, Task.created_at).where(Task.id.in_(task_ids))).all()
    durations: list[float] = []
    for task_id, created_at in created_rows:
        start = _aware(created_at)
        end = finished_at.get(task_id)
        if start and end and end >= start:
            durations.append((end - start).total_seconds())
    if not durations:
        return {"samples": 0, "average_seconds": None, "median_seconds": None, "max_seconds": None}
    durations.sort()
    middle = len(durations) // 2
    median = durations[middle] if len(durations) % 2 else (durations[middle - 1] + durations[middle]) / 2
    return {
        "samples": len(durations),
        "average_seconds": round(sum(durations) / len(durations), 1),
        "median_seconds": round(median, 1),
        "max_seconds": round(durations[-1], 1),
        "excluded_without_terminal_transition": db.scalar(select(func.count()).select_from(Task)) - len(durations),
    }


def review_outcomes(db: Session) -> dict[str, object]:
    rows = db.execute(select(ReviewRecord.verdict, func.count()).group_by(ReviewRecord.verdict)).all()
    by_verdict = {str(verdict): int(count) for verdict, count in rows}
    total = sum(by_verdict.values())
    approved = by_verdict.get("approved", 0)
    return {
        "total": total,
        "by_verdict": by_verdict,
        "approval_rate": round(approved / total, 3) if total else None,
        "source": "review_records; verdicts require concrete checks, so the rate reflects verified reviews only",
    }


def rework(db: Session) -> dict[str, object]:
    """Tasks that needed more than one attempt, measured from transitions."""
    rework_rows = db.execute(
        select(TaskTransition.task_id, func.count())
        .where(TaskTransition.to_state == "rework_required")
        .group_by(TaskTransition.task_id)
    ).all()
    task_total = db.scalar(select(func.count()).select_from(Task)) or 0
    return {
        "tasks_with_rework": len(rework_rows),
        "rework_events": sum(int(count) for _, count in rework_rows),
        "task_total": int(task_total),
        "share": round(len(rework_rows) / task_total, 3) if task_total else None,
        "source": "task_transitions rows entering rework_required",
    }


def approvals(db: Session) -> dict[str, object]:
    rows = db.execute(select(ApprovalRequest.status, func.count()).group_by(ApprovalRequest.status)).all()
    by_status = {str(status): int(count) for status, count in rows}
    by_kind = db.execute(select(ApprovalRequest.kind, func.count()).group_by(ApprovalRequest.kind)).all()
    return {
        "by_status": by_status,
        "by_kind": {str(kind): int(count) for kind, count in by_kind},
        "pending": by_status.get("pending", 0),
        "source": "approval_requests; approving a gated action does not execute it",
    }


def activity(db: Session, *, days: int = 14, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(timezone.utc)
    start = (current - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(AuditEvent.created_at).where(AuditEvent.created_at >= start)
    ).all()
    buckets: dict[str, int] = {}
    for offset in range(days):
        buckets[(start + timedelta(days=offset)).date().isoformat()] = 0
    for (created_at,) in rows:
        stamp = _aware(created_at)
        if stamp is None:
            continue
        key = stamp.date().isoformat()
        if key in buckets:
            buckets[key] += 1
    return {
        "days": days,
        "buckets": [{"date": day, "events": count} for day, count in buckets.items()],
        "total": len(rows),
        "source": "audit_events; every row is a recorded local action",
    }


def overview(db: Session, *, days: int = 14) -> dict[str, object]:
    checkpoint_count = db.scalar(select(func.count()).select_from(TaskCheckpoint)) or 0
    counts = {
        "projects": int(db.scalar(select(func.count()).select_from(Project)) or 0),
        "agents": int(db.scalar(select(func.count()).select_from(Agent)) or 0),
        "tasks": int(db.scalar(select(func.count()).select_from(Task)) or 0),
        "tasks_active": int(
            db.scalar(select(func.count()).select_from(Task).where(Task.state.in_(ACTIVE_STATES))) or 0
        ),
        "tasks_terminal": int(
            db.scalar(select(func.count()).select_from(Task).where(Task.state.in_(TERMINAL_STATES))) or 0
        ),
        "checkpoints": int(checkpoint_count),
    }
    return {
        "counts": counts,
        "throughput": throughput(db, days=days),
        "cycle_time": cycle_time(db),
        "reviews": review_outcomes(db),
        "rework": rework(db),
        "approvals": approvals(db),
        "activity": activity(db, days=days),
        "notes": [
            "All figures are computed from persisted rows; nothing is simulated or extrapolated.",
            "Provider cost analytics are absent because live provider traffic does not exist in this build.",
        ],
    }

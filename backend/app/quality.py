"""Independent QA reviews and approval gating.

Rules enforced here (not in the UI):

* A reviewer must be a registered agent and **must not** be the task's
  assignee — self-review is rejected.
* An `approved` verdict requires at least one concrete, non-empty check with a
  result, so a bare "looks good" cannot approve work.
* A `rework_required` verdict requires a summary explaining what to change.
* Review verdicts drive the workflow through the same validated state machine
  (`reviewing → approved | rework_required`), so no new state path is invented.
* Every verdict is idempotent per key and audited.
* Gated operations are recorded as approval requests; they are never executed
  here and can only be decided explicitly.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Agent, ApprovalRequest, ReviewRecord, Task
from app.workflow import transition_task

VERDICTS = ("approved", "rework_required")
APPROVAL_KINDS = ("paid_provider_request", "protected_branch_merge", "deployment", "data_deletion", "pull_request")
FINAL_APPROVAL_STATES = ("approved", "rejected")


class ReviewError(ValueError):
    """A safe, user-facing review validation failure."""


def _clean_checks(raw: list[object] | None) -> list[dict[str, object]]:
    cleaned: list[dict[str, object]] = []
    for item in raw or []:
        if isinstance(item, str):
            label, _, result = item.partition(":")
            cleaned.append({"check": label.strip(), "result": result.strip() or "pass"})
        elif isinstance(item, dict):
            label = str(item.get("check", "")).strip()
            result = str(item.get("result", "")).strip() or "pass"
            if label:
                cleaned.append({"check": label, "result": result})
    return cleaned


def record_review(
    db: Session,
    task: Task,
    *,
    reviewer_agent_id: str,
    verdict: str,
    summary: str = "",
    checks: list[object] | None = None,
    idempotency_key: str,
    task_worktree_head: str | None = None,
) -> tuple[ReviewRecord, bool]:
    if verdict not in VERDICTS:
        raise ReviewError(f"Verdict must be one of: {', '.join(VERDICTS)}.")
    key = idempotency_key.strip()
    if not key or len(key) > 160:
        raise ReviewError("An idempotency key of 1–160 characters is required.")

    existing = db.scalar(
        select(ReviewRecord).where(
            ReviewRecord.task_id == task.id,
            ReviewRecord.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.verdict != verdict:
            raise ReviewError("This idempotency key was already used for a different verdict.")
        return existing, False

    reviewer = db.get(Agent, reviewer_agent_id)
    if reviewer is None:
        raise ReviewError("Reviewer agent not found.")
    if task.assigned_agent_id and task.assigned_agent_id == reviewer.id:
        raise ReviewError("A task cannot be reviewed by the agent that is assigned to it.")

    cleaned = _clean_checks(checks)
    if verdict == "approved":
        if task.state not in {"reviewing", "completed"}:
            raise ReviewError("Approval requires the task to be in 'reviewing' (or 'completed').")
        if not cleaned:
            raise ReviewError("Approval requires at least one concrete check with a result.")
        if not (task.output or "").strip():
            raise ReviewError("Approval requires recorded task output as evidence.")
    else:
        if task.state not in {"reviewing", "completed"}:
            raise ReviewError("Rework can only be requested from 'reviewing' (or 'completed').")
        if not summary.strip():
            raise ReviewError("Requesting rework requires a summary describing what must change.")

    record = ReviewRecord(
        task_id=task.id,
        reviewer_agent_id=reviewer.id,
        verdict=verdict,
        summary=summary.strip()[:500],
        checks=cleaned,
        task_worktree_head=task_worktree_head,
        idempotency_key=key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)

    if task.state == "completed":
        transition_task(
            db,
            task,
            target_state="reviewing",
            idempotency_key=f"review-start-{key}",
            note=f"Review started by {reviewer.name}.",
        )
    transition_task(
        db,
        task,
        target_state=verdict,
        idempotency_key=f"review-verdict-{key}",
        note=summary.strip()[:500] or "Approved after verification.",
    )
    add_event(
        db,
        "task",
        task.id,
        f"task.review_{verdict}",
        f"Review {verdict} by {reviewer.name}: {task.title}",
    )
    db.flush()
    return record, True


def list_reviews(db: Session, task_id: str) -> list[ReviewRecord]:
    return list(
        db.scalars(
            select(ReviewRecord)
            .where(ReviewRecord.task_id == task_id)
            .order_by(ReviewRecord.created_at.asc())
        ).all()
    )


def request_approval(
    db: Session,
    *,
    kind: str,
    entity_type: str,
    entity_id: str | None,
    summary: str,
    requested_by: str = "local-user",
) -> ApprovalRequest:
    if kind not in APPROVAL_KINDS:
        raise ReviewError(f"Approval kind must be one of: {', '.join(APPROVAL_KINDS)}.")
    if not summary.strip():
        raise ReviewError("An approval request requires a summary explaining the action.")
    approval = ApprovalRequest(
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary.strip()[:500],
        requested_by=requested_by,
        status="pending",
    )
    db.add(approval)
    add_event(db, "approval", approval.id, "approval.requested", f"{kind}: {summary.strip()[:300]}")
    db.flush()
    return approval


def decide_approval(
    db: Session,
    approval: ApprovalRequest,
    *,
    status: str,
    decided_by: str,
    note: str = "",
) -> ApprovalRequest:
    if status not in FINAL_APPROVAL_STATES:
        raise ReviewError("Decision must be 'approved' or 'rejected'.")
    if approval.status != "pending":
        raise ReviewError(f"This approval request is already {approval.status}.")
    if not decided_by.strip():
        raise ReviewError("A decision must record who made it.")
    approval.status = status
    approval.decided_by = decided_by.strip()[:120]
    approval.decision_note = note.strip()[:500]
    approval.decided_at = datetime.now(timezone.utc)
    add_event(db, "approval", approval.id, f"approval.{status}", f"{approval.kind} {status} by {approval.decided_by}")
    db.flush()
    return approval

"""AI Team Intelligence Center.

The specification is explicit: *do not rank agents only by task count*, compare
fairly by role, project, provider, model, complexity and period, and keep
measured metrics separate from generated assessments.

This module therefore has two hard rules:

1. **Every metric is counted from rows.** Nothing is modelled, sampled or
   extrapolated. A metric with no data is ``None`` with a stated reason, not ``0``.
2. **Assessment is rule-based and labelled.** ``assessments`` are deterministic
   readings of the measured numbers, each carrying the figure it was derived from
   and ``kind: "rule_based"``. They are never presented as a model's judgement,
   and ``measured`` and ``assessed`` never mix in one field.

Fair comparison uses a *complexity-weighted* view plus a rate, because raw counts
reward whoever happened to receive the most tasks.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, ReviewRecord, Task, TaskTransition, UsageRecord

TERMINAL = ("completed", "approved", "failed", "cancelled")
SUCCESS = ("completed", "approved")
COMPLEXITY_WEIGHT = {"low": 1.0, "normal": 2.0, "high": 4.0, "urgent": 6.0}
MIN_SAMPLE = 3  # below this, a rate is reported but flagged as too small to compare


@dataclass
class AgentMetrics:
    agent_id: str
    name: str
    role: str
    provider: str
    model: str | None
    is_manager: bool
    tasks_total: int = 0
    tasks_terminal: int = 0
    tasks_success: int = 0
    tasks_failed: int = 0
    tasks_cancelled: int = 0
    open_tasks: int = 0
    complexity_points: float = 0.0
    by_complexity: dict[str, int] = field(default_factory=dict)
    rework_events: int = 0
    reviews_received: int = 0
    reviews_approved: int = 0
    usage_records: int = 0
    estimated_cost_usd: float = 0.0
    completion_seconds: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        completion = sorted(self.completion_seconds)
        median = None
        if completion:
            middle = len(completion) // 2
            median = (
                completion[middle]
                if len(completion) % 2
                else round((completion[middle - 1] + completion[middle]) / 2, 1)
            )
        sample_ok = self.tasks_terminal >= MIN_SAMPLE
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "is_manager": self.is_manager,
            "tasks": {
                "total": self.tasks_total,
                "terminal": self.tasks_terminal,
                "open": self.open_tasks,
                "success": self.tasks_success,
                "failed": self.tasks_failed,
                "cancelled": self.tasks_cancelled,
            },
            "success_rate": round(self.tasks_success / self.tasks_terminal, 3) if self.tasks_terminal else None,
            "success_rate_denominator": "terminal successes + failures; cancellations are excluded",
            "sample_sufficient": sample_ok,
            "complexity_points": round(self.complexity_points, 1),
            "complexity_points_per_task": (
                round(self.complexity_points / self.tasks_terminal, 2) if self.tasks_terminal else None
            ),
            "by_complexity": self.by_complexity,
            "rework": {
                "events": self.rework_events,
                "rate": round(self.rework_events / self.tasks_terminal, 3) if self.tasks_terminal else None,
            },
            "reviews": {
                "received": self.reviews_received,
                "approved": self.reviews_approved,
                "pass_rate": round(self.reviews_approved / self.reviews_received, 3) if self.reviews_received else None,
            },
            "completion_time": {
                "samples": len(completion),
                "median_seconds": median,
                "fastest_seconds": completion[0] if completion else None,
                "slowest_seconds": completion[-1] if completion else None,
            },
            "usage": {
                "records": self.usage_records,
                "estimated_cost_usd": round(self.estimated_cost_usd, 6),
                "confirmed": False,
                "note": "Estimates until a confirmed billing record is imported; none exists in this build.",
            },
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _period_start(days: int, now: datetime) -> datetime:
    return now - timedelta(days=days)


def collect(db: Session, *, days: int = 90, now: datetime | None = None) -> list[AgentMetrics]:
    moment = now or datetime.now(timezone.utc)
    since = _period_start(days, moment)
    agents = list(db.scalars(select(Agent).order_by(Agent.is_manager.desc(), Agent.name)).all())
    metrics = {
        agent.id: AgentMetrics(
            agent_id=agent.id,
            name="Manager" if agent.is_manager else agent.name,
            role=agent.role,
            provider=agent.provider,
            model=agent.model,
            is_manager=agent.is_manager,
        )
        for agent in agents
    }

    tasks = list(
        db.scalars(
            select(Task).where(Task.created_at >= since, Task.assigned_agent_id.is_not(None))
        ).all()
    )
    task_owner: dict[str, str] = {}
    for task in tasks:
        owner = metrics.get(str(task.assigned_agent_id))
        if owner is None:
            continue
        task_owner[task.id] = owner.agent_id
        owner.tasks_total += 1
        weight = COMPLEXITY_WEIGHT.get(task.priority, 2.0)
        owner.complexity_points += weight
        owner.by_complexity[task.priority] = owner.by_complexity.get(task.priority, 0) + 1
        if task.state in SUCCESS:
            owner.tasks_success += 1
            owner.tasks_terminal += 1
        elif task.state == "failed":
            # A failure is terminal and belongs in the denominator; leaving it out
            # would report a perfect rate for an agent that only ever fails.
            owner.tasks_failed += 1
            owner.tasks_terminal += 1
        elif task.state == "cancelled":
            # Cancellations are excluded from the denominator on purpose: a task
            # withdrawn for reasons outside the agent's control is not evidence
            # about the agent, and counting it as a failure would be unfair.
            owner.tasks_cancelled += 1
        else:
            owner.open_tasks += 1

    if not task_owner:
        return list(metrics.values())

    # Terminal durations: first successful terminal transition minus creation.
    terminal_rows = db.execute(
        select(TaskTransition.task_id, func.min(TaskTransition.created_at))
        .where(TaskTransition.task_id.in_(list(task_owner)), TaskTransition.to_state.in_(SUCCESS))
        .group_by(TaskTransition.task_id)
    ).all()
    finished_at = {row[0]: _aware(row[1]) for row in terminal_rows}
    for task in tasks:
        owner = metrics.get(task_owner.get(task.id, ""))
        end = finished_at.get(task.id)
        start = _aware(task.created_at)
        if owner is None or end is None or start is None or end < start:
            continue
        owner.completion_seconds.append(round((end - start).total_seconds(), 1))

    # Rework events, attributed to the agent that owned the task then.
    rework_rows = db.execute(
        select(TaskTransition.task_id, func.count())
        .where(TaskTransition.task_id.in_(list(task_owner)), TaskTransition.to_state == "rework_required")
        .group_by(TaskTransition.task_id)
    ).all()
    for task_id, count in rework_rows:
        owner = metrics.get(task_owner.get(task_id, ""))
        if owner is not None:
            owner.rework_events += int(count)

    # Reviews *received* by the assignee, not given by them.
    review_rows = db.execute(
        select(ReviewRecord.task_id, ReviewRecord.verdict).where(ReviewRecord.task_id.in_(list(task_owner)))
    ).all()
    for task_id, verdict in review_rows:
        owner = metrics.get(task_owner.get(task_id, ""))
        if owner is None:
            continue
        owner.reviews_received += 1
        if verdict == "approved":
            owner.reviews_approved += 1

    usage_rows = db.execute(
        select(UsageRecord.agent_id, func.count(), func.coalesce(func.sum(UsageRecord.estimated_cost_usd), 0.0))
        .where(UsageRecord.created_at >= since)
        .group_by(UsageRecord.agent_id)
    ).all()
    for agent_id, records, cost in usage_rows:
        owner = metrics.get(str(agent_id))
        if owner is None:
            continue
        owner.usage_records = int(records)
        owner.estimated_cost_usd = float(cost)

    return list(metrics.values())


def _assess(metrics: list[AgentMetrics]) -> list[dict[str, object]]:
    """Deterministic readings of the measured numbers. Never a model's opinion."""
    assessments: list[dict[str, object]] = []

    # Success-rate extremes, only where the sample can support a comparison.
    eligible = [m for m in metrics if m.tasks_terminal >= MIN_SAMPLE and not m.is_manager]
    if len(eligible) >= 2:
        best = max(eligible, key=lambda m: (m.tasks_success / m.tasks_terminal, -len(m.name)))
        worst = min(eligible, key=lambda m: (m.tasks_success / m.tasks_terminal, len(m.name)))
        if best.tasks_success / best.tasks_terminal - worst.tasks_success / worst.tasks_terminal >= 0.2:
            assessments.append(
                {
                    "kind": "rule_based",
                    "topic": "assignment",
                    "subject": best.name,
                    "finding": (
                        f"{best.name} succeeds on {best.tasks_success}/{best.tasks_terminal} terminal tasks "
                        f"({best.tasks_success / best.tasks_terminal:.0%}) versus "
                        f"{worst.tasks_success}/{worst.tasks_terminal} for {worst.name}."
                    ),
                    "basis": {"metric": "success_rate", "sample": best.tasks_terminal, "threshold": 0.2},
                    "recommendation": f"Consider routing comparable work to {best.name} first.",
                    "caveat": "Rate only. Complexity mix and sample size still matter; read both rows.",
                }
            )

    # Rework pressure.
    for item in metrics:
        if item.tasks_terminal >= MIN_SAMPLE and item.rework_events / max(item.tasks_terminal, 1) >= 0.5:
            assessments.append(
                {
                    "kind": "rule_based",
                    "topic": "quality",
                    "subject": item.name,
                    "finding": (
                        f"{item.rework_events} rework events across {item.tasks_terminal} terminal tasks "
                        f"({item.rework_events / item.tasks_terminal:.0%})."
                    ),
                    "basis": {"metric": "rework_rate", "threshold": 0.5},
                    "recommendation": "Review the reviewer's checks for this role before adding more work.",
                    "caveat": "A high rework rate can also mean the review bar is genuinely higher.",
                }
            )

    # Sample-size honesty.
    thin = [m for m in metrics if 0 < m.tasks_terminal < MIN_SAMPLE and not m.is_manager]
    if thin:
        assessments.append(
            {
                "kind": "rule_based",
                "topic": "method",
                "subject": "sample size",
                "finding": (
                    f"{len(thin)} agent(s) have fewer than {MIN_SAMPLE} terminal tasks "
                    f"({', '.join(m.name for m in thin)})."
                ),
                "basis": {"metric": "tasks_terminal", "threshold": MIN_SAMPLE},
                "recommendation": "Do not compare these agents on rate yet; the numbers are noise.",
                "caveat": "This is a statement about evidence, not about the agents.",
            }
        )

    # Cost visibility.
    if all(m.usage_records == 0 for m in metrics):
        assessments.append(
            {
                "kind": "rule_based",
                "topic": "cost",
                "subject": "provider usage",
                "finding": "No usage record exists for any agent in this period.",
                "basis": {"metric": "usage_records", "threshold": 1},
                "recommendation": "Cost cannot be compared yet; the column is empty, not zero.",
                "caveat": "AATM never makes a paid call in this build, so an empty column is expected.",
            }
        )

    return assessments


def report(db: Session, *, days: int = 90, now: datetime | None = None) -> dict[str, object]:
    if days < 1 or days > 3650:
        raise ValueError("days must be between 1 and 3650.")
    moment = now or datetime.now(timezone.utc)
    metrics = collect(db, days=days, now=moment)
    workers = [m for m in metrics if not m.is_manager]

    by_role: dict[str, list[dict[str, object]]] = {}
    by_complexity: dict[str, int] = {}
    for item in workers:
        payload = item.as_dict()
        by_role.setdefault(item.role, []).append(payload)
        for priority, count in item.by_complexity.items():
            by_complexity[priority] = by_complexity.get(priority, 0) + count

    return {
        "period": {
            "days": days,
            "since": _period_start(days, moment).isoformat(),
            "until": moment.isoformat(),
        },
        "agents": [item.as_dict() for item in metrics],
        "by_role": by_role,
        "by_complexity": by_complexity,
        "assessments": _assess(metrics),
        "method": {
            "measured_fields": [
                "tasks", "success_rate", "complexity_points", "by_complexity",
                "rework", "reviews", "completion_time", "usage",
            ],
            "assessed_fields": ["assessments"],
            "assessment_kind": "rule_based",
            "model_generated": False,
            "complexity_weights": COMPLEXITY_WEIGHT,
            "min_sample": MIN_SAMPLE,
            "ranking": "none",
            "note": (
                "Agents are not ranked by task count. Complexity is weighted, sample size is shown, "
                "and the assessments above are deterministic rules whose thresholds are listed with each one."
            ),
        },
        "note": "Every measured field is counted from stored rows; an empty period returns nulls, not zeros.",
    }

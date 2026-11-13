"""Deterministic Manager planning over persisted state.

This is a *rule-based* planner, not an LLM. It reads the real rows (tasks,
agents, dependencies, reviews) and produces:

* findings — concrete, checkable observations,
* proposed assignments — task → agent suggestions with the rule that produced
  them,
* proposed task order — a dependency-respecting sequence.

It writes **nothing** by default. Applying a plan is a separate, explicit call
that validates every proposal again, so a stale plan cannot silently reassign
work. Nothing here claims to "think" or to have used a model.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Agent, Task
from app.workflow import ALLOWED_TRANSITIONS, DEPENDENCY_SATISFIED_STATES

QUEUE_STATES = ("pending", "assigned", "rework_required")
ACTIVE_STATES = ("assigned", "running", "waiting")
PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class PlanningError(ValueError):
    """A safe, user-facing planning failure."""


@dataclass
class PlanProposal:
    task_id: str
    task_title: str
    current_state: str
    current_agent_id: str | None
    suggested_agent_id: str | None
    reason_code: str
    reason_data: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "current_state": self.current_state,
            "current_agent_id": self.current_agent_id,
            "suggested_agent_id": self.suggested_agent_id,
            "reason_code": self.reason_code,
            "reason_data": self.reason_data,
        }


def _active_agents(db: Session) -> list[Agent]:
    """Workers are a shared pool; AATM agents are not project-scoped yet."""
    return list(
        db.scalars(
            select(Agent).where(Agent.is_manager.is_(False), Agent.status != "offline").order_by(Agent.name)
        ).all()
    )


def _load(db: Session, project_id: str | None) -> list[Task]:
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    return list(db.scalars(query).all())


def dependency_order(tasks: list[Task]) -> tuple[list[str], list[str]]:
    """Topological order of queued work, plus any detected cycles.

    Cycles are reported rather than silently broken: a dependency cycle is a
    real planning defect that a human must resolve.
    """
    by_id = {task.id: task for task in tasks}
    pending = {task.id: [dep for dep in (task.dependencies or []) if dep in by_id] for task in tasks}
    ordered: list[str] = []
    ready = sorted(
        (task.id for task in tasks if not pending[task.id]),
        key=lambda task_id: (PRIORITY_ORDER.get(by_id[task_id].priority, 2), by_id[task_id].created_at),
    )
    while ready:
        current = ready.pop(0)
        if current in ordered:
            continue
        ordered.append(current)
        for task_id, deps in pending.items():
            if current in deps:
                deps.remove(current)
                if not deps and task_id not in ordered and task_id not in ready:
                    ready.append(task_id)
        ready.sort(key=lambda task_id: (PRIORITY_ORDER.get(by_id[task_id].priority, 2), by_id[task_id].created_at))
    cycles = sorted(set(by_id) - set(ordered))
    return ordered, cycles


def build_plan(db: Session, *, project_id: str | None = None) -> dict[str, object]:
    """Compute findings and proposals without writing anything."""
    tasks = _load(db, project_id)
    agents = _active_agents(db)
    agent_load: dict[str, int] = {agent.id: 0 for agent in agents}
    for task in tasks:
        if task.state in ACTIVE_STATES and task.assigned_agent_id in agent_load:
            agent_load[task.assigned_agent_id] += 1

    findings: list[dict[str, object]] = []
    proposals: list[PlanProposal] = []
    satisfied = {task.id for task in tasks if task.state in DEPENDENCY_SATISFIED_STATES}

    for task in tasks:
        blocking = [dep for dep in (task.dependencies or []) if dep not in satisfied]
        if task.state == "running" and task.assigned_agent_id is None:
            findings.append(
                {"code": "running_without_agent", "task_id": task.id, "task_title": task.title, "severity": "error"}
            )
        if task.state == "assigned" and blocking:
            findings.append(
                {
                    "code": "assigned_with_blocked_dependencies",
                    "task_id": task.id,
                    "task_title": task.title,
                    "severity": "warning",
                    "blocking": blocking,
                }
            )
        if task.state in QUEUE_STATES and task.assigned_agent_id is None and agents and not blocking:
            # Least-loaded active worker, ties broken by name for determinism.
            candidates = sorted(agents, key=lambda agent: (agent_load.get(agent.id, 0), agent.name))
            best = candidates[0] if candidates else None
            if best is not None:
                agent_load[best.id] = agent_load.get(best.id, 0) + 1
                proposals.append(
                    PlanProposal(
                        task_id=task.id,
                        task_title=task.title,
                        current_state=task.state,
                        current_agent_id=None,
                        suggested_agent_id=best.id,
                        reason_code="assign_least_loaded",
                        reason_data={"agent_load": agent_load[best.id], "active_agents": len(agents)},
                    )
                )
        if task.state == "rework_required" and "assigned" not in ALLOWED_TRANSITIONS.get("rework_required", ()):
            findings.append({"code": "rework_stuck", "task_id": task.id, "task_title": task.title, "severity": "error"})
        if task.state == "completed":
            findings.append(
                {"code": "awaiting_review", "task_id": task.id, "task_title": task.title, "severity": "info"}
            )

    ordered, cycles = dependency_order(tasks)
    if cycles:
        findings.append({"code": "dependency_cycle", "severity": "error", "task_ids": cycles})

    queued = [task for task in tasks if task.state in QUEUE_STATES]
    proposals.sort(key=lambda item: (PRIORITY_ORDER.get(next(t.priority for t in tasks if t.id == item.task_id), 2), item.task_title))

    payload = {
        "project_id": project_id,
        "task_total": len(tasks),
        "queued_total": len(queued),
        "active_agents": len(agents),
        "findings": findings,
        "proposals": [proposal.as_dict() for proposal in proposals],
        "order": ordered,
        "dependency_cycles": cycles,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "planner": "deterministic rules over persisted rows; no model was called",
        "applies_automatically": False,
    }
    payload["plan_id"] = hashlib.sha256(
        json.dumps({"proposals": payload["proposals"], "order": payload["order"], "findings": findings}, sort_keys=True).encode()
    ).hexdigest()[:16]
    return payload


def apply_plan(db: Session, plan: dict[str, object], *, actor: str = "manager") -> dict[str, object]:
    """Apply assignment proposals, re-validating each against current state."""
    if plan.get("plan_id") is None:
        raise PlanningError("A plan must be built before it can be applied.")
    applied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for proposal in plan.get("proposals", []):  # type: ignore[union-attr]
        task = db.get(Task, str(proposal["task_id"]))
        agent_id = proposal.get("suggested_agent_id")
        if task is None:
            skipped.append({"task_id": str(proposal["task_id"]), "reason": "missing_task"})
            continue
        if task.state not in QUEUE_STATES:
            skipped.append({"task_id": task.id, "reason": "state_changed"})
            continue
        if task.assigned_agent_id is not None:
            skipped.append({"task_id": task.id, "reason": "already_assigned"})
            continue
        agent = db.get(Agent, str(agent_id)) if agent_id else None
        if agent is None or agent.is_manager or agent.status == "offline":
            skipped.append({"task_id": task.id, "reason": "agent_unavailable"})
            continue
        # Taking planned work is a write: deny-by-default applies to the receiver,
        # so a plan cannot hand work to an agent that never declared the scope.
        from app.agents import AgentError, require_scope

        try:
            require_scope(agent, "task:write")
        except AgentError:
            skipped.append({"task_id": task.id, "reason": "agent_lacks_task_write_scope"})
            continue
        task.assigned_agent_id = agent.id
        if task.state == "pending":
            task.state = "assigned"
        applied.append({"task_id": task.id, "agent_id": agent.id})
        add_event(db, "task", task.id, "task.planned_assignment", f"Manager plan assigned '{task.title}' to {agent.name}.")
    db.flush()
    add_event(
        db,
        "system",
        None,
        "manager.plan_applied",
        f"Plan {plan.get('plan_id')} applied by {actor}: {len(applied)} assignment(s), {len(skipped)} skipped.",
    )
    return {"applied": applied, "skipped": skipped, "plan_id": plan.get("plan_id")}

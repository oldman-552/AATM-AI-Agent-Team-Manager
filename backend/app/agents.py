"""Agent lifecycle states and server-enforced permission scopes.

Two separate controls, both enforced here rather than in the UI:

**Lifecycle** — `idle → active → paused → active`, and any state → `disabled`.
A disabled agent cannot be assigned work (enforced by the assignment endpoints),
and transitions are validated so a client cannot invent a state.

**Permissions** — a small, explicit scope set. Scopes are *deny by default*:
an agent with no scopes can do nothing privileged. The checks are available to
any endpoint that performs a privileged action; today that means assignment and
plan application, and the same function is what a future executor must call.

Nothing here executes an agent. These are gates, not capabilities.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Agent, Task

STATES = ("idle", "active", "paused", "disabled")
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "idle": ("active", "disabled"),
    "active": ("paused", "disabled"),
    "paused": ("active", "disabled"),
    "disabled": (),  # re-enabling a disabled agent is a deliberate, separate decision
    "offline": (),
}

SCOPES = (
    "task:read",
    "task:write",
    "task:assign",
    "review:submit",
    "memory:write",
    "workspace:write",
)
MANAGER_ONLY_SCOPES = ("task:assign",)


class AgentError(ValueError):
    """A safe, user-facing agent lifecycle failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_scopes(scopes: list[str]) -> list[str]:
    cleaned: list[str] = []
    for scope in scopes:
        value = (scope or "").strip()
        if value not in SCOPES:
            raise AgentError(f"Unknown permission scope '{value}'. Allowed: {', '.join(SCOPES)}.")
        if value not in cleaned:
            cleaned.append(value)
    return sorted(cleaned)


def transition(db: Session, agent: Agent, *, target: str, note: str = "") -> Agent:
    current = agent.status if agent.status in TRANSITIONS else "idle"
    if target not in STATES:
        raise AgentError(f"State must be one of: {', '.join(STATES)}.")
    if target == current:
        raise AgentError(f"Agent is already '{current}'.")
    if target not in TRANSITIONS.get(current, ()):
        raise AgentError(
            f"Transition '{current}' → '{target}' is not allowed. Allowed: {', '.join(TRANSITIONS.get(current, ())) or 'none'}."
        )
    if agent.is_manager and target == "disabled":
        raise AgentError("The Manager identity cannot be disabled.")
    previous = agent.status
    agent.status = target
    add_event(
        db,
        "agent",
        agent.id,
        f"agent.{target}",
        f"Agent '{agent.name}' moved {previous} → {target}" + (f": {note.strip()[:200]}" if note.strip() else "."),
    )
    db.flush()
    return agent


def is_assignable(agent: Agent | None) -> tuple[bool, str]:
    if agent is None:
        return False, "agent_missing"
    if agent.is_manager:
        return False, "manager_is_not_a_worker"
    if agent.status == "disabled":
        return False, "agent_disabled"
    if agent.status == "paused":
        return False, "agent_paused"
    if agent.status == "offline":
        return False, "agent_offline"
    return True, "ok"


def require_scope(agent: Agent, scope: str) -> None:
    """Deny-by-default permission check. Raises ``AgentError`` when not granted."""
    if scope not in SCOPES:
        raise AgentError(f"Unknown permission scope '{scope}'.")
    granted = set(agent.permissions or [])
    if scope in MANAGER_ONLY_SCOPES and not agent.is_manager:
        raise AgentError(f"Scope '{scope}' is reserved for the Manager identity.")
    if scope not in granted:
        raise AgentError(f"Agent '{agent.name}' does not hold the '{scope}' permission.")


def can_assign(db: Session, agent_id: str) -> tuple[bool, str]:
    return is_assignable(db.get(Agent, agent_id))


def assign_task(db: Session, task: Task, agent_id: str | None) -> Task:
    """Assign or clear a task's agent, enforcing lifecycle state."""
    if agent_id is None:
        if task.assigned_agent_id is not None:
            add_event(db, "task", task.id, "task.unassigned", f"Task unassigned: {task.title}")
        task.assigned_agent_id = None
        db.flush()
        return task
    ok, reason = can_assign(db, agent_id)
    if not ok:
        raise AgentError(f"This agent cannot take work ({reason}).")
    agent = db.get(Agent, agent_id)
    assert agent is not None
    require_scope(agent, "task:write")
    task.assigned_agent_id = agent.id
    db.flush()
    return task


def blocked_agents(db: Session) -> list[dict[str, object]]:
    """Agents with open work but a non-working lifecycle state."""
    rows = db.execute(
        select(Task.assigned_agent_id, Task.state).where(
            Task.assigned_agent_id.is_not(None),
            Task.state.in_(("assigned", "running", "waiting")),
        )
    ).all()
    by_agent: dict[str, int] = {}
    for agent_id, _state in rows:
        by_agent[str(agent_id)] = by_agent.get(str(agent_id), 0) + 1
    blocked: list[dict[str, object]] = []
    for agent_id, open_tasks in by_agent.items():
        agent = db.get(Agent, agent_id)
        if agent is None:
            continue
        ok, reason = is_assignable(agent)
        if not ok:
            blocked.append(
                {"agent_id": agent.id, "agent_name": agent.name, "status": agent.status, "open_tasks": open_tasks, "reason": reason}
            )
    return blocked

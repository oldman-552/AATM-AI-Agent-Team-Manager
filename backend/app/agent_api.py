"""Agent lifecycle and permission endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents import SCOPES, AgentError, blocked_agents, scope_matrix, transition, validate_scopes
from app.audit import add_event
from app.agent_center import agent_center, center
from app.api import get_session
from app.models import Agent, AgentInstruction, Task

router = APIRouter(prefix="/api/v1/agents")


class AgentStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)


class AgentPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(max_length=len(SCOPES))


class InstructionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=20_000)
    task_id: str | None = None
    issued_by: str = Field(default="local-user", max_length=120)


class ReassignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    to_agent_id: str | None
    note: str = Field(min_length=1, max_length=200)


def _agent(db: Session, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@router.get("/scopes")
def list_scopes() -> dict[str, object]:
    """The nine permission levels, their scopes, and exactly what each gates."""
    return {"default": "deny", **scope_matrix()}


@router.patch("/{agent_id}/state")
def change_state(agent_id: str, payload: AgentStateChange, db: Session = Depends(get_session)) -> dict[str, object]:
    agent = _agent(db, agent_id)
    try:
        updated = transition(db, agent, target=payload.target_state, note=payload.note)
    except AgentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"agent_id": updated.id, "status": updated.status}


@router.patch("/{agent_id}/permissions")
def change_permissions(agent_id: str, payload: AgentPermissions, db: Session = Depends(get_session)) -> dict[str, object]:
    agent = _agent(db, agent_id)
    try:
        cleaned = validate_scopes(payload.permissions)
    except AgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    previous = list(agent.permissions or [])
    agent.permissions = cleaned
    from app.audit import add_event

    add_event(
        db,
        "agent",
        agent.id,
        "agent.permissions_changed",
        f"Permissions for '{agent.name}': {', '.join(previous) or 'none'} → {', '.join(cleaned) or 'none'}.",
    )
    db.commit()
    return {"agent_id": agent.id, "permissions": cleaned}


@router.get("/blocked")
def blocked(db: Session = Depends(get_session)) -> dict[str, object]:
    return {
        "agents": blocked_agents(db),
        "note": "Agents holding open work while paused, disabled or offline.",
    }


@router.get("/center")
def control_center(db: Session = Depends(get_session)) -> dict[str, object]:
    """Live Agent Control Center: real state, real activity, no invented progress."""
    return center(db)


@router.get("/{agent_id}/center")
def one_agent_center(agent_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    return agent_center(db, _agent(db, agent_id))


@router.get("/{agent_id}/instructions")
def list_instructions(agent_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    _agent(db, agent_id)
    rows = db.scalars(
        select(AgentInstruction)
        .where(AgentInstruction.agent_id == agent_id)
        .order_by(AgentInstruction.created_at.desc())
        .limit(50)
    ).all()
    return {
        "instructions": [
            {
                "id": row.id,
                "task_id": row.task_id,
                "instruction": row.instruction,
                "issued_by": row.issued_by,
                "delivered": row.delivered,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "delivery_note": "An instruction is recorded immediately. 'delivered' becomes true only when a real executor reports consuming it; no executor is configured.",
    }


@router.post("/{agent_id}/instructions", status_code=201)
def issue_instruction(agent_id: str, payload: InstructionRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    agent = _agent(db, agent_id)
    instruction = payload.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=422, detail="An instruction cannot be blank.")
    if payload.task_id is not None:
        task = db.get(Task, payload.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        if task.assigned_agent_id != agent.id:
            raise HTTPException(status_code=409, detail="That task is not assigned to this agent.")
    row = AgentInstruction(
        agent_id=agent.id,
        task_id=payload.task_id,
        instruction=instruction,
        issued_by=payload.issued_by,
    )
    db.add(row)
    db.flush()
    add_event(db, "agent", agent.id, "agent.instruction_issued", f"Instruction recorded for '{agent.name}': {instruction[:200]}")
    db.commit()
    return {
        "id": row.id,
        "agent_id": agent.id,
        "task_id": row.task_id,
        "delivered": False,
        "note": "Recorded for the next executor run. Nothing executes it in this build.",
    }


@router.post("/{agent_id}/reassign")
def reassign(agent_id: str, payload: ReassignRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    """Move one task to another agent (or back to the queue). Audited, never silent."""
    agent = _agent(db, agent_id)
    task = db.get(Task, payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.assigned_agent_id != agent.id:
        raise HTTPException(status_code=409, detail="That task is not assigned to this agent.")
    if task.state in ("completed", "approved", "cancelled"):
        raise HTTPException(status_code=409, detail=f"This task already reached '{task.state}'; reassigning finished work is not allowed.")
    if payload.to_agent_id is not None:
        target = db.get(Agent, payload.to_agent_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target agent not found.")
        if target.is_manager:
            raise HTTPException(status_code=409, detail="The Manager does not take worker assignments.")
        if target.id == agent.id:
            raise HTTPException(status_code=409, detail="That task is already assigned to this agent.")
        if target.status in ("paused", "disabled", "offline"):
            raise HTTPException(status_code=409, detail=f"Target agent is '{target.status}' and cannot take work.")
        if task.state == "running" and task.lease_owner:
            raise HTTPException(status_code=409, detail="Task is running under a lease. Request cancellation or wait for the lease to expire before reassigning.")
    # Reassignment moves work *away* from this agent, so it is an operator
    # decision, not the agent granting work to itself. The receiving agent is
    # still checked: `assign_task` requires task:write of whoever takes the work.
    previous = task.assigned_agent_id
    task.assigned_agent_id = payload.to_agent_id
    if task.state == "running" and payload.to_agent_id is None:
        task.state = "assigned"
    add_event(
        db,
        "task",
        task.id,
        "task.reassigned",
        f"Task reassigned from '{agent.name}' to '{payload.to_agent_id or 'unassigned'}': {payload.note[:160]}",
    )
    db.commit()
    return {
        "task_id": task.id,
        "from_agent_id": previous,
        "to_agent_id": task.assigned_agent_id,
        "state": task.state,
        "note": "Reassignment is recorded and audited. No work was started.",
    }

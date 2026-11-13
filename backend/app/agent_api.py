"""Agent lifecycle and permission endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents import SCOPES, AgentError, blocked_agents, transition, validate_scopes
from app.api import get_session
from app.models import Agent

router = APIRouter(prefix="/api/v1/agents")


class AgentStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)


class AgentPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(max_length=len(SCOPES))


def _agent(db: Session, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@router.get("/scopes")
def list_scopes() -> dict[str, object]:
    return {"scopes": list(SCOPES), "default": "deny", "note": "No scope is granted unless explicitly assigned."}


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

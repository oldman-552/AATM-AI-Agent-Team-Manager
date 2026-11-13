"""AI Project Builder endpoints: propose a plan, review it, then apply it."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.blueprints import MAX_IDEA, BlueprintError, apply_blueprint, build_blueprint

router = APIRouter(prefix="/api/v1/blueprints")


class BlueprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idea: str = Field(min_length=20, max_length=MAX_IDEA)
    scale: Literal["prototype", "mvp", "production"] = "mvp"
    stack: Literal["python-react", "node-react", "python-only"] = "python-react"
    data_layer: Literal["sqlite", "postgres"] = "sqlite"
    team_size: int = Field(default=3, ge=1, le=20)
    project_name: str | None = Field(default=None, max_length=120)


class BlueprintApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: dict
    project_name: str | None = Field(default=None, max_length=120)
    create_project: bool = True
    confirmed: bool
    actor: str = Field(default="local-user", max_length=120)


@router.post("")
def propose(payload: BlueprintRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    """Generate a reviewable blueprint. Writes nothing."""
    try:
        return build_blueprint(
            db,
            idea=payload.idea,
            scale=payload.scale,
            stack=payload.stack,
            data_layer=payload.data_layer,
            team_size=payload.team_size,
            project_name=payload.project_name,
        )
    except BlueprintError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply")
def apply(payload: BlueprintApply, db: Session = Depends(get_session)) -> dict[str, object]:
    """Create the project and tasks from a reviewed plan. Requires explicit confirmation."""
    if payload.confirmed is not True:
        raise HTTPException(
            status_code=409,
            detail="Applying a blueprint creates real tasks. Re-send with confirmed=true after reviewing the plan.",
        )
    try:
        result = apply_blueprint(
            db,
            payload.plan,
            project_name=payload.project_name,
            create_project=payload.create_project,
            actor=payload.actor,
        )
    except BlueprintError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return result

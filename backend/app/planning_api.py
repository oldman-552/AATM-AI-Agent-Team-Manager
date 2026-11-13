"""Manager planning endpoints: deterministic proposals, explicit application."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.models import Project
from app.planning import PlanningError, apply_plan, build_plan

router = APIRouter(prefix="/api/v1/planning")


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: dict
    actor: str = Field(default="manager", max_length=120)


@router.get("/proposals")
def proposals(project_id: str | None = None, db: Session = Depends(get_session)) -> dict[str, object]:
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return build_plan(db, project_id=project_id)


@router.post("/apply")
def apply(payload: ApplyRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    if payload.plan.get("project_id") is not None and db.get(Project, str(payload.plan["project_id"])) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        result = apply_plan(db, payload.plan, actor=payload.actor)
    except PlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return result

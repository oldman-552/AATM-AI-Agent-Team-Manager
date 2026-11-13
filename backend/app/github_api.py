"""Pull-request plan endpoints. Planning and gating only — no network, no push."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.github_plans import (
    EXECUTION_AVAILABLE,
    EXECUTION_REASON,
    GithubError,
    create_plan,
    decide_plan,
    plan_payload,
    refresh_status,
)
from app.models import GithubPullRequest, Project

router = APIRouter(prefix="/api/v1/projects/{project_id}/pull-requests")


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    base_branch: str = Field(default="main", max_length=121)
    head_branch: str = Field(min_length=1, max_length=121)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20_000)
    requested_by: str = Field(default="local-user", max_length=120)


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(approved|rejected)$")
    decided_by: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _plan(db: Session, project_id: str, plan_id: str) -> GithubPullRequest:
    plan = db.get(GithubPullRequest, plan_id)
    if plan is None or plan.project_id != project_id:
        raise HTTPException(status_code=404, detail="Pull request plan not found.")
    return plan


@router.get("")
def list_plans(project_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    _project(db, project_id)
    rows = db.scalars(
        select(GithubPullRequest)
        .where(GithubPullRequest.project_id == project_id)
        .order_by(GithubPullRequest.created_at.desc())
    ).all()
    plans = [refresh_status(db, row) for row in rows]
    db.commit()
    return {
        "plans": [plan_payload(plan) for plan in plans],
        "execution_available": EXECUTION_AVAILABLE,
        "execution_reason": EXECUTION_REASON,
    }


@router.post("", status_code=201)
def create(project_id: str, payload: PlanCreate, db: Session = Depends(get_session)) -> dict[str, object]:
    project = _project(db, project_id)
    try:
        plan, approval = create_plan(
            db,
            project,
            owner=payload.owner,
            repo=payload.repo,
            base_branch=payload.base_branch,
            head_branch=payload.head_branch,
            title=payload.title,
            body=payload.body,
            requested_by=payload.requested_by,
        )
    except GithubError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"plan": plan_payload(plan), "approval": {"id": approval.id, "status": approval.status}}


@router.post("/{plan_id}/decision")
def decide(
    project_id: str,
    plan_id: str,
    payload: PlanDecision,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    _project(db, project_id)
    plan = _plan(db, project_id, plan_id)
    try:
        updated = decide_plan(db, plan, status=payload.status, decided_by=payload.decided_by, note=payload.note)
    except GithubError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"plan": plan_payload(updated)}


@router.post("/{plan_id}/execute")
def execute(project_id: str, plan_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    """Always refuses, honestly: live execution is not implemented here."""
    _project(db, project_id)
    plan = refresh_status(db, _plan(db, project_id, plan_id))
    db.commit()
    raise HTTPException(
        status_code=409,
        detail={
            "executed": False,
            "execution_available": EXECUTION_AVAILABLE,
            "reason": EXECUTION_REASON,
            "plan_status": plan.status,
        },
    )

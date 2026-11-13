"""HTTP endpoints for real project, agent, task, and dashboard state."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.audit import add_event
from app.models import Agent, AuditEvent, Project, Task
from app.roles import DEFAULT_AGENT_ROLES
from app.schemas import (
    AgentCreate,
    AgentRead,
    AuditEventRead,
    ProjectCreate,
    ProjectRead,
    TaskAssignment,
    TaskCreate,
    TaskRead,
)

router = APIRouter(prefix="/api/v1")


def get_session(request: Request):
    factory = request.app.state.session_factory
    db: Session = factory()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health(request: Request, db: Session = Depends(get_session)) -> dict[str, object]:
    """Report application and database health based on an actual DB query."""
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "application": request.app.title,
        "version": __version__,
        "database": "ok",
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_session)) -> dict[str, object]:
    """Return real counts and a short event list from the persistent store."""
    project_count = db.scalar(select(func.count()).select_from(Project)) or 0
    agent_count = db.scalar(select(func.count()).select_from(Agent)) or 0
    worker_count = db.scalar(
        select(func.count()).select_from(Agent).where(Agent.is_manager.is_(False))
    ) or 0
    task_count = db.scalar(select(func.count()).select_from(Task)) or 0

    agent_status_rows = db.execute(
        select(Agent.status, func.count()).group_by(Agent.status)
    ).all()
    task_state_rows = db.execute(
        select(Task.state, func.count()).group_by(Task.state)
    ).all()
    recent_events = db.scalars(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(8)
    ).all()

    return {
        "projects": {"total": project_count},
        "agents": {
            "total": agent_count,
            "workers": worker_count,
            "max_workers": 20,
            "by_status": {str(key): value for key, value in agent_status_rows},
        },
        "tasks": {
            "total": task_count,
            "by_state": {str(key): value for key, value in task_state_rows},
        },
        "recent_events": [AuditEventRead.model_validate(event).model_dump(mode="json") for event in recent_events],
    }


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc()).limit(limit)).all())


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_session)) -> Project:
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    db.flush()
    add_event(db, "project", project.id, "project.created", f"Project created: {project.name}")
    db.commit()
    db.refresh(project)
    return project


@router.get("/agent-roles")
def list_agent_roles() -> list[dict[str, str]]:
    return DEFAULT_AGENT_ROLES


@router.get("/agents", response_model=list[AgentRead])
def list_agents(
    db: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.is_manager.desc(), Agent.created_at.asc()).limit(limit)).all())


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_session)) -> Agent:
    worker_count = db.scalar(
        select(func.count()).select_from(Agent).where(Agent.is_manager.is_(False))
    ) or 0
    if worker_count >= 20:
        raise HTTPException(status_code=409, detail="The maximum of 20 registered worker agents has been reached.")

    agent = Agent(
        name=payload.name,
        role=payload.role,
        description=payload.description,
        system_instructions=payload.system_instructions,
        provider=payload.provider,
        model=payload.model,
        status="idle",
        is_manager=False,
    )
    db.add(agent)
    db.flush()
    add_event(db, "agent", agent.id, "agent.registered", f"Worker agent registered: {agent.name}")
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    db: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit)).all())


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_session)) -> Task:
    if payload.project_id is not None and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if payload.assigned_agent_id is not None and db.get(Agent, payload.assigned_agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    if len(set(payload.dependencies)) != len(payload.dependencies):
        raise HTTPException(status_code=422, detail="Task dependencies must not contain duplicates.")
    if payload.dependencies:
        existing_ids = set(db.scalars(select(Task.id).where(Task.id.in_(payload.dependencies))).all())
        missing_ids = set(payload.dependencies) - existing_ids
        if missing_ids:
            raise HTTPException(status_code=404, detail="One or more task dependencies were not found.")

    task = Task(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        state="assigned" if payload.assigned_agent_id else "pending",
        assigned_agent_id=payload.assigned_agent_id,
        dependencies=payload.dependencies,
        acceptance_criteria=payload.acceptance_criteria,
    )
    db.add(task)
    db.flush()
    add_event(db, "task", task.id, "task.created", f"Task created: {task.title}")
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}/assignment", response_model=TaskRead)
def assign_task(task_id: str, payload: TaskAssignment, db: Session = Depends(get_session)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if payload.assigned_agent_id is not None:
        agent = db.get(Agent, payload.assigned_agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found.")
        task.assigned_agent_id = agent.id
        task.state = "assigned"
        summary = f"Task assigned to {agent.name}: {task.title}"
    else:
        task.assigned_agent_id = None
        task.state = "pending"
        summary = f"Task unassigned: {task.title}"

    add_event(db, "task", task.id, "task.assignment_changed", summary)
    db.commit()
    db.refresh(task)
    return task


@router.get("/events", response_model=list[AuditEventRead])
def list_events(
    db: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all())

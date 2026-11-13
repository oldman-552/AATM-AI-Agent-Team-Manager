"""Live Agent Control Center: real backend state, never fabricated activity.

Everything returned here is read from rows that exist:

* ``Agent.status`` — the recorded lifecycle state,
* open tasks assigned to the agent — its current work,
* ``audit_events`` scoped to the agent or its tasks — the latest observable activity,
* ``usage_records`` — estimated cost, and whether any of it was *confirmed*,
* ``task_leases`` — whether the agent currently holds a lease,
* ``browser_profiles`` — profile ownership (never a claim that a browser runs).

Absent data is reported as absent. A field is ``None`` when AATM genuinely has
no record of it, and the payload carries an explicit honesty block so the UI
cannot silently present an estimate as a measurement.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AuditEvent, BrowserProfile, Task, UsageRecord

OPEN_STATES = ("assigned", "running", "waiting", "rework_required", "reviewing")
FINAL_STATES = ("completed", "approved", "cancelled", "failed")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def _open_tasks(db: Session, agent_id: str) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.assigned_agent_id == agent_id, Task.state.in_(OPEN_STATES))
            .order_by(Task.updated_at.desc())
        ).all()
    )


def _latest_activity(db: Session, agent: Agent, task_ids: list[str]) -> dict[str, object] | None:
    """Newest audit row about this agent, or about one of its tasks."""
    about_agent = (AuditEvent.entity_type == "agent") & (AuditEvent.entity_id == agent.id)
    if task_ids:
        condition = about_agent | ((AuditEvent.entity_type == "task") & (AuditEvent.entity_id.in_(task_ids)))
    else:
        condition = about_agent
    event = db.scalars(
        select(AuditEvent).where(condition).order_by(AuditEvent.created_at.desc()).limit(1)
    ).first()
    if event is None:
        return None
    return {
        "at": _iso(event.created_at),
        "event_type": event.event_type,
        "summary": event.summary,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
    }


def _usage(db: Session, agent_id: str) -> dict[str, object]:
    row = db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.estimated_cost_usd), 0.0),
            func.coalesce(func.sum(UsageRecord.confirmed_cost_usd), 0.0),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        ).where(UsageRecord.agent_id == agent_id)
    ).one()
    records, estimated, confirmed, in_tokens, out_tokens = row
    return {
        "records": int(records),
        "estimated_cost_usd": round(float(estimated), 6),
        "confirmed_cost_usd": round(float(confirmed), 6),
        "confirmed_records": int(
            db.scalar(
                select(func.count(UsageRecord.id)).where(
                    UsageRecord.agent_id == agent_id, UsageRecord.confirmed_cost_usd.is_not(None)
                )
            )
            or 0
        ),
        "input_tokens": int(in_tokens),
        "output_tokens": int(out_tokens),
        "cost_source": "estimate_only" if int(records) and not confirmed else ("mixed" if int(records) else "none"),
    }


def _execution_seconds(tasks: list[Task]) -> dict[str, object]:
    """Wall-clock since the oldest open task started moving. Not CPU time."""
    if not tasks:
        return {"seconds": None, "basis": "no open task"}
    oldest = min(task.updated_at for task in tasks)
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - oldest).total_seconds())
    return {"seconds": max(seconds, 0), "basis": "since the oldest open task last changed"}


def agent_center(db: Session, agent: Agent) -> dict[str, object]:
    tasks = _open_tasks(db, agent.id)
    task_ids = [task.id for task in tasks]
    current = tasks[0] if tasks else None
    latest = _latest_activity(db, agent, task_ids)
    usage = _usage(db, agent.id)
    profiles = list(
        db.scalars(select(BrowserProfile).where(BrowserProfile.agent_id == agent.id).order_by(BrowserProfile.name)).all()
    )
    lease_owner_task = next(
        (task for task in tasks if task.lease_owner is not None), None
    )

    return {
        "agent_id": agent.id,
        "name": agent.is_manager and "Manager" or agent.name,
        "role": agent.role,
        "is_manager": agent.is_manager,
        "status": agent.status,
        "provider": agent.provider,
        "model": agent.model,
        "current_task": (
            {
                "task_id": current.id,
                "title": current.title,
                "state": current.state,
                "priority": current.priority,
                "updated_at": _iso(current.updated_at),
                "lease_owner": current.lease_owner,
            }
            if current
            else None
        ),
        "open_task_count": len(tasks),
        "open_tasks": [
            {"task_id": task.id, "title": task.title, "state": task.state, "priority": task.priority}
            for task in tasks
        ],
        "latest_activity": latest,
        "execution_time": _execution_seconds(tasks),
        "usage": usage,
        "leases": {
            "held": lease_owner_task is not None,
            "task_id": lease_owner_task.id if lease_owner_task else None,
            "owner": lease_owner_task.lease_owner if lease_owner_task else None,
            "expires_at": _iso(lease_owner_task.lease_expires_at) if lease_owner_task else None,
        },
        "browser": {
            "profiles": len(profiles),
            "names": [profile.name for profile in profiles],
            "automation_available": False,
            "note": "AATM records profile directories; it does not launch or drive a browser in this build.",
        },
        "authentication": {
            "registered": True,
            "provider_configured": agent.provider != "unconfigured",
            "model": agent.model,
            "note": "Registration exists. A provider credential is never exposed here, and none is inspected.",
        },
        "errors": (
            [{"task_id": current.id, "state": current.state, "error": current.error}]
            if current is not None and current.error
            else []
        ),
        "history": [
            {
                "task_id": task.id,
                "title": task.title,
                "state": task.state,
                "updated_at": _iso(task.updated_at),
            }
            for task in db.scalars(
                select(Task)
                .where(Task.assigned_agent_id == agent.id, Task.state.in_(FINAL_STATES))
                .order_by(Task.updated_at.desc())
                .limit(5)
            ).all()
        ],
        "controls": {
            # What the backend can actually do, so the UI never offers a fake button.
            "pause": agent.status in ("active", "idle") and not agent.is_manager,
            "resume": agent.status == "paused",
            "stop": agent.status in ("active", "paused", "idle") and not agent.is_manager,
            "reassign": bool(tasks),
            "instructions": True,
            "open_browser": False,
            "open_workspace": None,
        },
        "honesty": {
            "activity_source": "audit_events",
            "cost_kind": "estimate" if usage["confirmed_records"] == 0 else "estimate+confirmed",
            "execution_time_kind": "wall_clock_not_cpu",
            "browser_automation": False,
            "note": "Every field above maps to a stored row or is null. No activity is simulated.",
        },
    }


def center(db: Session, *, limit: int = 100) -> dict[str, object]:
    agents = list(db.scalars(select(Agent).order_by(Agent.is_manager.desc(), Agent.created_at.asc()).limit(limit)).all())
    return {
        "agents": [agent_center(db, agent) for agent in agents],
        "total": len(agents),
        "note": "Live state read from the database at request time.",
    }

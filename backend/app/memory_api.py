"""Memory API with strict project isolation.

`project_id` is always an explicit query parameter; there is no implicit
"current project" that could leak rows across projects. Passing another
project's id is the only way to read its memory, and that is a caller decision
recorded by the caller's own access control — the isolation guarantee is that
memory never leaks through global search, listing, or keyword retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.memory import (
    SCOPES,
    MemoryError,
    MemoryWrite,
    delete_memory,
    export_memory,
    get_visible,
    history,
    list_memory,
    rollback,
    search_memory,
    upsert_memory,
)
from app.models import MemoryEntry

router = APIRouter(prefix="/api/v1/memory")


class MemoryUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    scope: str = Field(default="project", pattern="^(global|project|agent|task|decision)$")
    key: str | None = Field(default=None, max_length=120)
    project_id: str | None = Field(default=None, max_length=36)
    agent_id: str | None = Field(default=None, max_length=36)
    task_id: str | None = Field(default=None, max_length=36)
    tags: list[str] = Field(default_factory=list, max_length=20)


def _serialize(row: MemoryEntry) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "scope": row.scope,
        "key": row.key,
        "title": row.title,
        "content": row.content,
        "agent_id": row.agent_id,
        "task_id": row.task_id,
        "tags": row.tags,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("")
def list_entries(
    project_id: str | None = Query(default=None, max_length=36),
    scope: str | None = Query(default=None, max_length=20),
    include_global: bool = Query(default=True),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        rows = list_memory(db, project_id=project_id, scope=scope, include_global=include_global)
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "entries": [_serialize(row) for row in rows],
        "scopes": list(SCOPES),
        "isolation": "Only global entries and entries of the requested project are returned.",
    }


@router.post("", status_code=201)
def create_or_version(payload: MemoryUpsert, db: Session = Depends(get_session)) -> dict[str, object]:
    try:
        row, created = upsert_memory(
            db,
            MemoryWrite(
                title=payload.title,
                content=payload.content,
                scope=payload.scope,
                key=payload.key,
                project_id=payload.project_id,
                agent_id=payload.agent_id,
                task_id=payload.task_id,
                tags=tuple(payload.tags),
            ),
        )
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return {"entry": _serialize(row), "created": created}


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    project_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="A non-blank search query is required.")
    results = search_memory(db, project_id=project_id, query=q, limit=limit)
    return {
        "results": [{"entry": _serialize(row), "score": score} for row, score in results],
        "query": q,
        "retrieval": "deterministic keyword overlap; no embeddings and no network call",
    }


@router.get("/export")
def export(project_id: str | None = Query(default=None, max_length=36), db: Session = Depends(get_session)) -> dict[str, object]:
    return {"entries": export_memory(db, project_id), "project_id": project_id}


@router.get("/{entry_id}")
def get_entry(
    entry_id: str,
    project_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    row = get_visible(db, entry_id, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory entry not found for this project.")
    return {"entry": _serialize(row), "history": [
        {"version": item.version, "title": item.title, "content": item.content, "created_at": item.created_at.isoformat()}
        for item in history(db, row)
    ]}


@router.post("/{entry_id}/rollback/{version}")
def rollback_entry(
    entry_id: str,
    version: int,
    project_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    row = get_visible(db, entry_id, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory entry not found for this project.")
    try:
        updated = rollback(db, row, version)
    except MemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    db.refresh(updated)
    return {"entry": _serialize(updated)}


@router.delete("/{entry_id}")
def delete_entry(
    entry_id: str,
    project_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    row = get_visible(db, entry_id, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory entry not found for this project.")
    delete_memory(db, row)
    db.commit()
    return {"deleted": True, "id": entry_id}

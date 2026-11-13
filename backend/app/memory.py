"""Project-isolated memory with scoped retrieval and versioning.

Scopes:

* ``global``   — shared workspace context (no project isolation).
* ``project``  — visible only inside its project (strict isolation).
* ``agent``    — tied to one agent, still project-bound when a project is set.
* ``task``     — tied to one task, still project-bound when a project is set.
* ``decision`` — architectural decisions, project-bound.

Isolation rule: any non-global entry is only retrievable (and only editable)
within its own project. A cross-project read never leaks rows; it simply finds
nothing. Every write bumps a monotonic version and appends history, so a
memory value can be traced and rolled back deliberately.

Retrieval is a deterministic local keyword/overlap score — no embeddings, no
network, no provider call.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import MemoryEntry, MemoryVersion, Project

SCOPES = ("global", "project", "agent", "task", "decision")
MAX_TITLE = 200
MAX_CONTENT = 20000
_TOKEN = re.compile(r"[A-Za-z0-9_\u0600-\u06FF][A-Za-z0-9_\-\u0600-\u06FF]*")


class MemoryError(ValueError):
    """A safe, user-facing memory validation failure."""


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text or "")]


@dataclass(frozen=True)
class MemoryWrite:
    title: str
    content: str
    scope: str = "project"
    key: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    tags: tuple[str, ...] = ()


def _validate(db: Session, entry: MemoryWrite) -> None:
    title = entry.title.strip()
    content = entry.content.strip()
    if not title or len(title) > MAX_TITLE:
        raise MemoryError(f"A memory title of 1–{MAX_TITLE} characters is required.")
    if not content or len(content) > MAX_CONTENT:
        raise MemoryError(f"Memory content of 1–{MAX_CONTENT} characters is required.")
    if entry.scope not in SCOPES:
        raise MemoryError(f"Scope must be one of: {', '.join(SCOPES)}.")
    if entry.scope != "global" and not entry.project_id:
        raise MemoryError("Project-bound memory requires a project_id; only 'global' scope may omit it.")
    if entry.project_id and db.get(Project, entry.project_id) is None:
        raise MemoryError("Project not found.")
    if entry.scope == "agent" and not entry.agent_id:
        raise MemoryError("Agent-scoped memory requires an agent_id.")
    if entry.scope == "task" and not entry.task_id:
        raise MemoryError("Task-scoped memory requires a task_id.")


def upsert_memory(db: Session, entry: MemoryWrite) -> tuple[MemoryEntry, bool]:
    """Create or version a memory entry. Returns (entry, created)."""
    _validate(db, entry)
    key = (entry.key or "").strip() or None
    existing: MemoryEntry | None = None
    if key:
        existing = db.scalar(
            select(MemoryEntry).where(
                MemoryEntry.project_id == entry.project_id,
                MemoryEntry.key == key,
            )
        )

    now = datetime.now(timezone.utc)
    if existing is None:
        row = MemoryEntry(
            project_id=entry.project_id,
            scope=entry.scope,
            key=key,
            title=entry.title.strip(),
            content=entry.content.strip(),
            agent_id=entry.agent_id,
            task_id=entry.task_id,
            tags=list(entry.tags),
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        db.add(
            MemoryVersion(
                entry_id=row.id,
                version=1,
                content=row.content,
                title=row.title,
                created_at=now,
            )
        )
        add_event(db, "memory", row.id, "memory.created", f"Memory created ({entry.scope}): {row.title}")
        db.flush()
        return row, True

    row = existing
    row.title = entry.title.strip()
    row.content = entry.content.strip()
    row.scope = entry.scope
    row.tags = list(entry.tags)
    row.version = int(row.version or 1) + 1
    row.updated_at = now
    if entry.agent_id:
        row.agent_id = entry.agent_id
    if entry.task_id:
        row.task_id = entry.task_id
    db.add(
        MemoryVersion(
            entry_id=row.id,
            version=row.version,
            content=row.content,
            title=row.title,
            created_at=now,
        )
    )
    add_event(db, "memory", row.id, "memory.versioned", f"Memory updated to v{row.version}: {row.title}")
    db.flush()
    return row, False


def list_memory(
    db: Session,
    *,
    project_id: str | None,
    scope: str | None = None,
    include_global: bool = True,
) -> list[MemoryEntry]:
    """List memory visible from one project, enforcing isolation."""
    if scope is not None and scope not in SCOPES:
        raise MemoryError(f"Unknown scope '{scope}'.")
    statement = select(MemoryEntry)
    if project_id is None:
        statement = statement.where(MemoryEntry.scope == "global")
    elif include_global:
        statement = statement.where(
            (MemoryEntry.project_id == project_id) | (MemoryEntry.scope == "global")
        )
    else:
        statement = statement.where(MemoryEntry.project_id == project_id)
    if scope:
        statement = statement.where(MemoryEntry.scope == scope)
    statement = statement.order_by(MemoryEntry.updated_at.desc())
    return list(db.scalars(statement).all())


def get_visible(db: Session, entry_id: str, project_id: str | None) -> MemoryEntry | None:
    row = db.get(MemoryEntry, entry_id)
    if row is None:
        return None
    if row.scope == "global":
        return row
    if project_id is None or row.project_id != project_id:
        return None
    return row


def search_memory(
    db: Session,
    *,
    project_id: str | None,
    query: str,
    limit: int = 10,
) -> list[tuple[MemoryEntry, float]]:
    """Deterministic keyword retrieval restricted to visible memory."""
    terms = _tokens(query)
    if not terms:
        return []
    scored: list[tuple[MemoryEntry, float]] = []
    for row in list_memory(db, project_id=project_id):
        haystack = f"{row.title} {row.content} {' '.join(row.tags or [])}".lower()
        hits = sum(1 for term in terms if term in haystack)
        if not hits:
            continue
        title_hits = sum(1 for term in terms if term in row.title.lower())
        score = hits / len(terms) + 0.25 * title_hits
        scored.append((row, round(score, 4)))
    scored.sort(key=lambda item: (-item[1], item[0].title))
    return scored[: max(1, limit)]


def history(db: Session, entry: MemoryEntry) -> list[MemoryVersion]:
    return list(
        db.scalars(
            select(MemoryVersion)
            .where(MemoryVersion.entry_id == entry.id)
            .order_by(MemoryVersion.version.asc())
        ).all()
    )


def rollback(db: Session, entry: MemoryEntry, version_number: int) -> MemoryEntry:
    """Restore content from an earlier version as a *new* version (never deletes history)."""
    target = db.scalar(
        select(MemoryVersion).where(
            MemoryVersion.entry_id == entry.id,
            MemoryVersion.version == version_number,
        )
    )
    if target is None:
        raise MemoryError("Version not found for this memory entry.")
    entry.title = target.title
    entry.content = target.content
    entry.version = int(entry.version or 1) + 1
    entry.updated_at = datetime.now(timezone.utc)
    db.add(
        MemoryVersion(
            entry_id=entry.id,
            version=entry.version,
            content=entry.content,
            title=entry.title,
            created_at=entry.updated_at,
        )
    )
    add_event(db, "memory", entry.id, "memory.rolled_back", f"Memory rolled back to v{version_number} as v{entry.version}.")
    db.flush()
    return entry


def delete_memory(db: Session, entry: MemoryEntry) -> None:
    """Delete an entry and its history after an explicit caller decision."""
    db.query(MemoryVersion).filter(MemoryVersion.entry_id == entry.id).delete()
    add_event(db, "memory", entry.id, "memory.deleted", f"Memory deleted: {entry.title}")
    db.delete(entry)
    db.flush()


def export_memory(db: Session, project_id: str | None) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "scope": row.scope,
            "key": row.key,
            "title": row.title,
            "content": row.content,
            "tags": row.tags,
            "version": row.version,
            "project_id": row.project_id,
            "agent_id": row.agent_id,
            "task_id": row.task_id,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in list_memory(db, project_id=project_id)
    ]

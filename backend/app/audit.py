"""Shared audit-event writer for local domain changes."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditEvent


def add_event(
    db: Session,
    entity_type: str,
    entity_id: str | None,
    event_type: str,
    summary: str,
) -> None:
    """Queue one observable event. Never include secrets or credential values."""
    db.add(
        AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            summary=summary[:500],
            created_at=datetime.now(timezone.utc),
        )
    )

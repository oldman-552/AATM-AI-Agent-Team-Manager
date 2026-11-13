"""Server-sent events for audit-log changes.

The specification asks for real-time updates "where appropriate". The honest
constraint here is that the build is local and SQLite-backed: there is no bus to
subscribe to, so this streams by *polling the audit table* and telling the client
exactly that in the `hello` frame. It is deliberately not called a push feed.

Design points that matter:

* **Resumable cursor.** Every frame carries the event id. A client that
  reconnects sends `Last-Event-ID` (or `?last_event_id=`) and receives only what
  it missed, rather than a duplicate storm or a silent gap. Resumption keys on
  the `(created_at, id)` pair, not the timestamp alone: two events can share a
  timestamp, and a cursor on time alone would drop or repeat one at the boundary.
* **Bounded lifetime.** A stream closes itself after ``max_seconds``. Long-lived
  streams leak database sessions behind proxies and look healthy while dead.
* **Heartbeat.** A comment line every ``heartbeat_seconds`` keeps intermediaries
  from dropping an idle connection, and lets a client tell "quiet" from "stuck".
* **Bounded work per tick.** Each poll is a single indexed query with a limit, so
  a large backlog cannot balloon memory.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .api import get_session
from .models import AuditEvent

router = APIRouter(prefix="/api/v1/events")

# Hard limits, exported so tests and docs share one source of truth.
MAX_STREAM_SECONDS = 300
MAX_HEARTBEAT_SECONDS = 60
DEFAULT_POLL_SECONDS = 1.0
MAX_BATCH = 200


def _frame(event_name: str, payload: dict[str, object], event_id: str | None = None) -> str:
    """Serialise one SSE frame. Data must be a single line per field."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(payload, separators=(',', ':'))}")
    return "\n".join(lines) + "\n\n"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def fetch_after(session: Session, cursor: tuple[datetime, str] | None, limit: int = MAX_BATCH) -> list[AuditEvent]:
    """Events after the cursor, oldest first (portable keyset pagination)."""
    statement = select(AuditEvent)
    if cursor is not None:
        created_at, event_id = cursor
        statement = statement.where(
            or_(
                AuditEvent.created_at > created_at,
                and_(AuditEvent.created_at == created_at, AuditEvent.id > event_id),
            )
        )
    statement = statement.order_by(AuditEvent.created_at, AuditEvent.id).limit(limit)
    return list(session.scalars(statement).all())


def current_cursor(session: Session) -> tuple[datetime, str] | None:
    row = session.execute(
        select(AuditEvent.created_at, AuditEvent.id).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def stream_from(
    session_factory,
    cursor: tuple[datetime, str] | None,
    *,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    heartbeat_seconds: int = 15,
    max_seconds: int = MAX_STREAM_SECONDS,
) -> Iterator[str]:
    """Yield SSE frames: a hello, then new events, with heartbeats in between."""
    started = time.monotonic()
    last_beat = 0.0
    yield _frame(
        "hello",
        {
            "transport": "server-sent-events",
            "source": "audit_events table, polled",
            "delivery": "poll",
            "poll_seconds": poll_seconds,
            "max_seconds": max_seconds,
            "resume_with": "Last-Event-ID header or last_event_id query parameter",
            "note": "Events are polled from the database, not pushed by a broker.",
        },
    )

    while True:
        elapsed = time.monotonic() - started
        if elapsed >= max_seconds:
            yield _frame("close", {"reason": "max_seconds_reached", "elapsed_seconds": round(elapsed, 1)})
            return

        with session_factory() as session:
            events = fetch_after(session, cursor)
            # Fetch one extra so a full batch can be flagged as possibly truncated.
            more = len(events) == MAX_BATCH
            payloads = [
                {
                    "id": event.id,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "event_type": event.event_type,
                    "summary": event.summary,
                    "created_at": _iso(event.created_at),
                }
                for event in events
            ]
            if events:
                cursor = (events[-1].created_at, events[-1].id)

        for payload in payloads:
            yield _frame("audit", payload, event_id=str(payload["id"]))
        if more:
            yield _frame("more", {"batch": MAX_BATCH, "note": "poll again immediately for the backlog"})

        now = time.monotonic()
        if now - last_beat >= heartbeat_seconds:
            last_beat = now
            yield _frame("heartbeat", {"elapsed_seconds": round(elapsed, 1), "cursor_event_id": cursor[1] if cursor else None})

        time.sleep(poll_seconds)


@router.get("/stream")
def stream_events(
    last_event_id: str | None = Query(default=None, description="Event id to resume after, or 0/omit for live-only."),
    poll_seconds: float = Query(default=DEFAULT_POLL_SECONDS, ge=0.25, le=10),
    heartbeat_seconds: int = Query(default=15, ge=5, le=MAX_HEARTBEAT_SECONDS),
    max_seconds: int = Query(default=MAX_STREAM_SECONDS, ge=2, le=MAX_STREAM_SECONDS),
    db: Session = Depends(get_session),
) -> StreamingResponse:
    """Stream audit events as they are recorded.

    Without a cursor the stream starts live (no history replay); with a cursor it
    replays what was missed and then continues.
    """
    if last_event_id in (None, "", "0"):
        cursor = current_cursor(db)
    else:
        row = db.execute(
            select(AuditEvent.created_at, AuditEvent.id).where(AuditEvent.id == last_event_id)
        ).first()
        # An unknown id is not an error: the event may have been pruned. Resume
        # from the start of what still exists rather than silently skipping it.
        cursor = (row[0], row[1]) if row else None

    factory = _session_factory(db)
    return StreamingResponse(
        stream_from(
            factory,
            cursor,
            poll_seconds=poll_seconds,
            heartbeat_seconds=heartbeat_seconds,
            max_seconds=max_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tell nginx-style proxies not to buffer, or events arrive in bursts.
            "X-Accel-Buffering": "no",
        },
    )


def _session_factory(db: Session):
    """Rebuild a factory from the request's session so the generator owns its own.

    The request session is closed when the response starts, so a generator that
    held it would use a dead connection mid-stream.
    """
    bind = db.get_bind()
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=bind, autoflush=False, autocommit=False, expire_on_commit=False)

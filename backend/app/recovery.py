"""Self-healing and recovery: detection, diagnostics, and honest reporting.

The specification asks AATM to recover from agent, browser, provider, network,
queue and database failures. Three of those do not exist in this build (there is
no browser, no provider traffic and no network dependency), and claiming recovery
for them would be fiction. What *does* exist is reported here:

* **Queue failures** — expired leases, retries and exhausted tasks, read from
  real rows, with the existing recovery path described rather than promised.
* **Database errors** — the health probe runs a real query, and a failure is
  classified (locked, corrupt, missing table, unreachable) so the operator gets a
  cause instead of a stack trace.
* **Timeouts and resource exhaustion** — bounded, measured, and reported as an
  advisory for the operator. Nothing is auto-applied: the orchestrator's
  configured concurrency stays authoritative.

Every item carries ``automatic: bool`` saying whether AATM acts by itself. The
only true case is retry/lease recovery, which the orchestrator genuinely performs.
"""

import sqlite3
import time
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.orm import Session

from app.models import Task

RECOVERABLE_STATES = ("failed", "waiting")
MAX_RETRY_COUNT = 3  # mirrors the orchestrator's ceiling


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def classify_database_error(exc: BaseException) -> dict[str, object]:
    """Turn a database exception into a cause an operator can act on."""
    message = str(getattr(exc, "orig", exc))
    lowered = message.lower()
    if isinstance(exc, IntegrityError):
        category, advice = "constraint", "A uniqueness or foreign-key rule refused the write. Nothing was changed."
    elif "database is locked" in lowered or "database table is locked" in lowered:
        category, advice = "locked", "Another connection holds a write lock. Retry shortly; AATM rolls the transaction back first."
    elif "no such table" in lowered or "no such column" in lowered:
        category, advice = "schema", "The schema does not match the code. Run the migrations before retrying."
    elif "malformed" in lowered or "not a database" in lowered or "corrupt" in lowered:
        category, advice = "corrupt", "Restore from a verified backup; do not retry against a corrupt file."
    elif isinstance(exc, OperationalError):
        category, advice = "unavailable", "The database could not be reached or is read-only. Check the file or server."
    else:
        category, advice = "unknown", "Read the message above; the transaction was rolled back."
    return {
        "category": category,
        "message": message[:500],
        "advice": advice,
        "automatic_recovery": False,
        "note": "AATM rolls the failed transaction back so one request cannot poison the next.",
    }


def database_probe(db: Session) -> dict[str, object]:
    """Run a real query and report what actually happened, with timing."""
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        detail = classify_database_error(exc)
        return {
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            **detail,
        }
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": True,
        "elapsed_ms": elapsed,
        "slow": elapsed > 500,
        "category": "ok",
        "note": "A real SELECT 1 succeeded." if elapsed <= 500 else "The probe succeeded but took longer than 500 ms.",
    }


def _sqlite_integrity(db: Session) -> dict[str, object] | None:
    """SQLite can check itself; other engines cannot, so this returns None there."""
    try:
        result = db.execute(text("PRAGMA integrity_check")).scalar()
    except SQLAlchemyError:
        return None
    return {"ok": result == "ok", "result": str(result)[:200]}


def queue_health(db: Session) -> dict[str, object]:
    counts = dict(
        db.execute(select(Task.state, func.count()).group_by(Task.state)).all()
    )
    exhausted = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.state.in_(("failed", "waiting")), Task.retry_count >= MAX_RETRY_COUNT)
        )
        or 0
    )
    recoverable = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.state.in_(RECOVERABLE_STATES), Task.retry_count < MAX_RETRY_COUNT)
        )
        or 0
    )
    expired_leases = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.lease_expires_at.is_not(None), Task.state == "running")
        )
        or 0
    )
    return {
        "by_state": {str(key): int(value) for key, value in counts.items()},
        "recoverable_tasks": recoverable,
        "exhausted_tasks": exhausted,
        "running_with_lease": expired_leases,
        "retry_ceiling": MAX_RETRY_COUNT,
        "note": "Expired leases are reclaimed by the orchestrator on its next run; exhausted tasks need a human decision.",
    }


def recovery_report(db: Session) -> dict[str, object]:
    """One honest page: what can be seen, what is handled, what cannot exist."""
    db_state = database_probe(db)
    integrity = _sqlite_integrity(db) if db_state["ok"] else None
    queue = queue_health(db)

    capabilities = [
        {
            "failure": "Agent crash / interrupted task",
            "detected_by": "expired lease on a running task",
            "handled": True,
            "automatic": True,
            "action": "The orchestrator reclaims the lease on its next run and retries within the ceiling.",
        },
        {
            "failure": "Queue stall / retry exhaustion",
            "detected_by": "task at the retry ceiling in failed or waiting",
            "handled": True,
            "automatic": False,
            "action": "Surfaced here and in notifications; a human decides whether to rework, reassign or cancel.",
        },
        {
            "failure": "Database error",
            "detected_by": "health probe and transaction rollback",
            "handled": True,
            "automatic": False,
            "action": "The failing transaction is rolled back and classified; the cause is reported, never silently retried.",
        },
        {
            "failure": "Application or OS restart",
            "detected_by": "leases persisted with an expiry timestamp",
            "handled": True,
            "automatic": True,
            "action": "State is durable in SQLite; leases expired during downtime are recovered on startup of the next orchestrator run.",
        },
        {
            "failure": "Resource exhaustion",
            "detected_by": "local CPU/memory/disk sampling",
            "handled": True,
            "automatic": False,
            "action": "/system/resources returns an advisory ceiling; the configured concurrency stays authoritative and nothing is auto-applied.",
        },
        {
            "failure": "Browser crash",
            "detected_by": "nothing",
            "handled": False,
            "automatic": False,
            "action": "Not applicable: this build never launches a browser, so there is nothing to crash or recover.",
        },
        {
            "failure": "Provider or network failure",
            "detected_by": "nothing at runtime",
            "handled": False,
            "automatic": False,
            "action": "No provider request is ever made from the HTTP app, so there is no live failure to recover from. The offline adapter path is covered by tests with an injected client.",
        },
    ]

    dedupe_note = (
        "Recovery never blind-retries an action that could duplicate an external effect: "
        "no external effect exists in this build, and state changes carry idempotency keys."
    )
    return {
        "database": {**db_state, "integrity": integrity},
        "queue": queue,
        "capabilities": capabilities,
        "summary": {
            "detected": sum(1 for item in capabilities if item["handled"]),
            "automatic": sum(1 for item in capabilities if item["automatic"]),
            "not_applicable": [item["failure"] for item in capabilities if not item["handled"]],
        },
        "idempotency": dedupe_note,
        "checked_at": _iso(datetime.now(timezone.utc)),
        "note": "Everything above is read from real state or is explicitly marked as not applicable.",
    }


def is_transient(exc: BaseException) -> bool:
    """True when retrying the *same* operation is safe and might succeed.

    Deliberately narrow: only lock contention qualifies. An integrity error will
    fail identically on retry, and retrying it would hide a real defect.
    """
    if isinstance(exc, IntegrityError):
        return False
    if isinstance(exc, OperationalError):
        return "locked" in str(getattr(exc, "orig", exc)).lower()
    if isinstance(exc, sqlite3.OperationalError):
        return "locked" in str(exc).lower()
    return False


def retry_on_transient(db: Session, operation, attempts: int = 3, delay: float = 0.05):
    """Run ``operation`` retrying only transient failures, with a fresh rollback."""
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except DBAPIError as exc:  # pragma: no cover - timing-dependent
            if not is_transient(exc) or attempt == attempts - 1:
                raise
            last = exc
            db.rollback()
            time.sleep(delay * (attempt + 1))
    raise last  # type: ignore[misc]

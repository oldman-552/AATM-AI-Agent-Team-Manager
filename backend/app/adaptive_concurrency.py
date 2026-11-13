"""Opt-in, fail-safe resource-aware cap for one orchestrator dispatch pass.

The default remains the existing configured batch size. When explicitly enabled,
local CPU/memory/disk telemetry may only reduce that batch, never increase it.
This is a per-process dispatch guard, not a cross-worker distributed semaphore.
"""

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Task
from app.resources import recommend_concurrency, sample_resources

ADAPTIVE_CONCURRENCY_FLAG = "AATM_ADAPTIVE_CONCURRENCY"
MAX_CONCURRENCY_FLAG = "AATM_MAX_CONCURRENCY"
DEFAULT_MAX_CONCURRENCY = 1
MAX_CONFIGURED_CONCURRENCY = 20


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def adaptive_concurrency_enabled() -> bool:
    """Resource-based reduction is off unless an operator explicitly opts in."""
    return _enabled(os.getenv(ADAPTIVE_CONCURRENCY_FLAG, settings.adaptive_concurrency))


def configured_max_concurrency() -> int:
    """Read a bounded operator cap; malformed/out-of-range values fail closed to 1."""
    try:
        value = int(os.getenv(MAX_CONCURRENCY_FLAG, settings.max_concurrency))
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONCURRENCY
    if not 1 <= value <= MAX_CONFIGURED_CONCURRENCY:
        return DEFAULT_MAX_CONCURRENCY
    return value


def _resource_path(db: Session) -> Path:
    """Sample disk pressure beside a file-backed SQLite DB where possible."""
    try:
        url = db.get_bind().url
        if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
            return Path(url.database).expanduser().resolve().parent
    except (AttributeError, OSError, RuntimeError):
        pass
    return Path.cwd()


def concurrency_policy(
    db: Session,
    *,
    in_flight: int | None = None,
    for_run: bool = False,
) -> dict[str, object]:
    """Describe and calculate the run's maximum dispatch count.

    With adaptation off, preserve the configured cap exactly. With it on,
    sample local resources and subtract currently running tasks from the
    recommendation. ``for_run`` distinguishes a computed status preview from a
    policy actually passed to the orchestrator. A zero available slot means the
    run may recover/inspect state but must not claim another task.
    """
    configured = configured_max_concurrency()
    running = (
        len(db.scalars(select(Task.id).where(Task.state == "running")).all())
        if in_flight is None
        else in_flight
    )
    in_flight = max(0, int(running))
    enabled = adaptive_concurrency_enabled()
    if not enabled:
        return {
            "adaptive_enabled": False,
            "configured_max": configured,
            "recommended_max": None,
            "in_flight": in_flight,
            "effective_dispatch_budget": configured,
            "applied_automatically": False,
            "reasons": [f"Adaptive reduction is disabled; using configured cap {configured}."],
        }

    snapshot = sample_resources(_resource_path(db))
    recommendation = recommend_concurrency(
        snapshot,
        configured_max=configured,
        in_flight=in_flight,
    )
    recommended = int(recommendation["recommended_concurrency"])
    return {
        "adaptive_enabled": True,
        "configured_max": configured,
        "recommended_max": recommended,
        "in_flight": in_flight,
        "effective_dispatch_budget": max(0, recommended - in_flight),
        "applied_automatically": bool(for_run),
        "reasons": list(recommendation["reasons"]),
        "snapshot": snapshot.as_dict(),
        "note": (
            "The local sample only reduces this run's dispatch budget; it cannot exceed the configured cap. "
            "This is per process, not a distributed multi-worker limit."
        ),
    }

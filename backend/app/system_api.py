"""Local resource telemetry and an adaptive-concurrency recommendation."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import get_session
from app.core.config import settings
from app.models import Task
from app.orchestrator import LEASE_SECONDS, MAX_RETRIES
from app.resources import recommend_concurrency, sample_resources

router = APIRouter(prefix="/api/v1/system")


def _data_dir() -> Path:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1)).expanduser().parent
    return Path.home()


@router.get("/resources")
def resources(
    configured_max: int = Query(default=2, ge=1, le=20),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Local CPU/memory/disk sample plus a bounded recommendation (never auto-applied)."""
    snapshot = sample_resources(_data_dir())
    in_flight = len(list(db.scalars(select(Task).where(Task.state == "running")).all()))
    return {
        "snapshot": snapshot.as_dict(),
        "recommendation": recommend_concurrency(snapshot, configured_max=configured_max, in_flight=in_flight),
        "orchestrator": {
            "default_lease_seconds": LEASE_SECONDS,
            "max_retries": MAX_RETRIES,
            "note": "The orchestrator's configured concurrency is authoritative; this endpoint only advises.",
        },
        "telemetry": "Measured locally with the Python standard library; nothing is uploaded.",
    }

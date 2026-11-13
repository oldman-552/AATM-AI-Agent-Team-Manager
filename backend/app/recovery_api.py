"""Self-healing and recovery endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import get_session
from app.recovery import database_probe, recovery_report

router = APIRouter(prefix="/api/v1/recovery")


@router.get("")
def report(db: Session = Depends(get_session)) -> dict[str, object]:
    """Detection, diagnostics and an honest capability table."""
    return recovery_report(db)


@router.get("/database")
def database(db: Session = Depends(get_session)) -> dict[str, object]:
    """A real query with timing and a classified cause when it fails."""
    return database_probe(db)

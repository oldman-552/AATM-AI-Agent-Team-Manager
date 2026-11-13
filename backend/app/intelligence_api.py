"""AI Team Intelligence Center endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import get_session
from app.intelligence import report

router = APIRouter(prefix="/api/v1/intelligence")


@router.get("")
def get_report(
    days: int = Query(default=90, ge=1, le=3650),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    """Measured agent performance by role and complexity, with rule-based assessments.

    Measured figures and assessments are separate fields: nothing here is a
    model's judgement, and no overall ranking is produced.
    """
    try:
        return report(db, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

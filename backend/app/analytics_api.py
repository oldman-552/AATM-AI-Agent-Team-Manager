"""Read-only analytics endpoints derived from persisted records."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics import activity, approvals, cycle_time, overview, review_outcomes, rework, throughput
from app.api import get_session

router = APIRouter(prefix="/api/v1/analytics")


@router.get("")
def get_overview(days: int = Query(default=14, ge=1, le=90), db: Session = Depends(get_session)) -> dict[str, object]:
    return overview(db, days=days)


@router.get("/throughput")
def get_throughput(days: int = Query(default=14, ge=1, le=90), db: Session = Depends(get_session)) -> dict[str, object]:
    return throughput(db, days=days)


@router.get("/cycle-time")
def get_cycle_time(db: Session = Depends(get_session)) -> dict[str, object]:
    return cycle_time(db)


@router.get("/reviews")
def get_reviews(db: Session = Depends(get_session)) -> dict[str, object]:
    return review_outcomes(db)


@router.get("/rework")
def get_rework(db: Session = Depends(get_session)) -> dict[str, object]:
    return rework(db)


@router.get("/approvals")
def get_approvals(db: Session = Depends(get_session)) -> dict[str, object]:
    return approvals(db)


@router.get("/activity")
def get_activity(days: int = Query(default=14, ge=1, le=90), db: Session = Depends(get_session)) -> dict[str, object]:
    return activity(db, days=days)

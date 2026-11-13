"""Notifications derived from real pending work."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.notifications import (
    NotificationError,
    mark_all_read,
    mark_read,
    prune_reads,
    summary,
)

router = APIRouter(prefix="/api/v1/notifications")


class MarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=100)


@router.get("")
def list_notifications(db: Session = Depends(get_session)) -> dict[str, object]:
    return summary(db)


@router.post("/read")
def read_notifications(payload: MarkRead, db: Session = Depends(get_session)) -> dict[str, object]:
    try:
        created = mark_read(db, payload.ids)
    except NotificationError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"marked_read": created, **summary(db)}


@router.post("/read-all")
def read_all(db: Session = Depends(get_session)) -> dict[str, object]:
    result = mark_all_read(db)
    db.commit()
    return {**result, **summary(db)}


@router.delete("/read-state")
def prune(
    older_than_days: int = Query(default=90, ge=1, le=3650),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    removed = prune_reads(db, older_than_days=older_than_days)
    db.commit()
    return {"removed": removed}

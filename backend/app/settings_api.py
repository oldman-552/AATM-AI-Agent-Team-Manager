"""Non-secret preference settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.app_settings import DEFAULTS, SettingsError, export_settings, read_settings, reset_settings, write_settings

router = APIRouter(prefix="/api/v1/settings")


class SettingsUpdate(BaseModel):
    """Allow-listed preferences. Extra fields are rejected, not silently ignored."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, max_length=5)
    theme: str | None = Field(default=None, max_length=10)
    page_size: int | None = None
    notification_poll_seconds: int | None = None
    checkpoint_retention: int | None = None
    backup_retention: int | None = None
    updated_by: str = Field(default="local-user", max_length=120)


@router.get("")
def get_settings(db: Session = Depends(get_session)) -> dict[str, object]:
    return {
        "settings": read_settings(db),
        "defaults": DEFAULTS,
        "note": "Preferences only. Credentials never live here; providers use env:/keyring references.",
    }


@router.patch("")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_session)) -> dict[str, object]:
    data = payload.model_dump(exclude_none=True)
    updated_by = str(data.pop("updated_by", "local-user"))
    if not data:
        raise HTTPException(status_code=422, detail="Provide at least one setting to change.")
    try:
        updated = write_settings(db, data, updated_by=updated_by)
    except SettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"settings": updated}


@router.post("/reset")
def reset(db: Session = Depends(get_session)) -> dict[str, object]:
    restored = reset_settings(db)
    db.commit()
    return {"settings": restored}


@router.get("/export")
def export(db: Session = Depends(get_session)) -> dict[str, object]:
    return export_settings(db)

"""Browser profile endpoints: registry, isolation and exclusivity.

No endpoint here launches or drives a browser. See `browser_profiles.py`.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.browser_profiles import (
    ProfileError,
    create_profile,
    delete_profile,
    find_profile,
    list_profiles,
    lock,
    profile_payload,
    transition,
    unlock,
    update_profile,
)
from app.models import Agent

router = APIRouter(prefix="/api/v1/browser-profiles")


def default_profiles_root() -> Path:
    configured = os.environ.get("AATM_BROWSER_PROFILES_ROOT")
    if configured:
        return Path(configured).expanduser()
    home = Path(os.environ.get("AATM_HOME", Path.home() / ".aatm")).expanduser()
    return home / "browser-profiles"


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    label: str = Field(default="", max_length=80)
    agent_id: str | None = Field(default=None, max_length=36)
    isolation: str = Field(default="per_profile", pattern="^(per_profile|shared_readonly)$")


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=80)
    agent_id: str | None = Field(default=None, max_length=36)
    clear_agent: bool = False


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)


class LockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locked_by: str = Field(min_length=1, max_length=120)


def _profile(db: Session, profile_id: str):
    try:
        return find_profile(db, profile_id)
    except ProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def index(agent_id: str | None = None, db: Session = Depends(get_session)) -> dict[str, object]:
    root = default_profiles_root()
    return {
        "profiles": list_profiles(db, root=root, agent_id=agent_id),
        "automation_available": False,
        "note": "Profiles store an isolated directory and metadata only; no browser is launched and no credentials are read.",
    }


@router.post("", status_code=201)
def create(payload: ProfileCreate, db: Session = Depends(get_session)) -> dict[str, object]:
    root = default_profiles_root()
    if payload.agent_id is not None and db.get(Agent, payload.agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    try:
        profile = create_profile(
            db,
            root=root,
            name=payload.name,
            label=payload.label,
            agent_id=payload.agent_id,
            isolation=payload.isolation,
        )
    except ProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"profile": profile_payload(profile, root=root)}


@router.get("/{profile_id}")
def show(profile_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    profile = _profile(db, profile_id)
    return {"profile": profile_payload(profile, root=default_profiles_root())}


@router.patch("/{profile_id}")
def update(profile_id: str, payload: ProfileUpdate, db: Session = Depends(get_session)) -> dict[str, object]:
    profile = _profile(db, profile_id)
    try:
        updated = update_profile(
            db,
            profile,
            label=payload.label,
            agent_id=payload.agent_id,
            clear_agent=payload.clear_agent,
        )
    except ProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"profile": profile_payload(updated, root=default_profiles_root())}


@router.patch("/{profile_id}/state")
def change_state(profile_id: str, payload: StateChange, db: Session = Depends(get_session)) -> dict[str, object]:
    profile = _profile(db, profile_id)
    try:
        updated = transition(db, profile, target=payload.target_state, note=payload.note)
    except ProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"profile": profile_payload(updated, root=default_profiles_root())}


@router.post("/{profile_id}/lock")
def lock_profile(profile_id: str, payload: LockRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    profile = _profile(db, profile_id)
    try:
        updated = lock(db, profile, locked_by=payload.locked_by)
    except ProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"profile": profile_payload(updated, root=default_profiles_root())}


@router.post("/{profile_id}/unlock")
def unlock_profile(profile_id: str, db: Session = Depends(get_session)) -> dict[str, object]:
    profile = _profile(db, profile_id)
    try:
        updated = unlock(db, profile)
    except ProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"profile": profile_payload(updated, root=default_profiles_root())}


@router.delete("/{profile_id}")
def remove(
    profile_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    profile = _profile(db, profile_id)
    try:
        result = delete_profile(db, profile, root=default_profiles_root(), confirm=confirm)
    except ProfileError as exc:
        raise HTTPException(status_code=409 if confirm else 422, detail=str(exc)) from exc
    db.commit()
    return result

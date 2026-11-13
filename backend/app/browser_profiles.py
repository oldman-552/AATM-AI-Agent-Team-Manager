"""Browser profile registry: metadata and isolated on-disk profile homes.

What this does
--------------
It manages the *registry* of browser profiles: a stable id, a label, a
per-profile directory that cannot escape the configured root, which agent owns
it, and lifecycle state. It can also report whether the directory exists and
how large it is.

What this deliberately does **not** do
-------------------------------------
* It never launches a browser, and it never drives one. Playwright is not a
  dependency of this build and nothing here pretends automation works.
* It never reads, parses or returns cookie/cookie jars, saved logins, session
  storage or any credential material. A profile is an opaque directory; AATM
  reports only existence, size and timestamps.
* It never records a "logged in" status. `session_state` is always
  `not_inspected`, because inspecting it would mean reading credentials we
  refuse to handle.
* Deletion requires an explicit confirmation flag, because a profile directory
  can contain irreplaceable user data.

This is the honest half of "multiple browser profiles": real, isolated storage
plus real lifecycle, with zero fabricated automation capability.
"""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Agent, BrowserProfile

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,59}$")
LABEL_MAX = 80
STATES = ("created", "ready", "locked", "archived")
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "created": ("ready", "locked", "archived"),
    "ready": ("locked", "archived"),
    "locked": ("ready", "archived"),
    "archived": (),
}


class ProfileError(ValueError):
    """A safe, user-facing profile failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_name(name: str) -> str:
    candidate = (name or "").strip()
    if not NAME_PATTERN.fullmatch(candidate) or ".." in candidate:
        raise ProfileError(
            "Profile names may contain letters, digits, spaces, '.', '_' and '-' (max 60), and cannot contain '..'."
        )
    return candidate


def profile_dir(root: Path, profile_id: str) -> Path:
    """Resolve a profile directory and refuse to escape the root."""
    resolved_root = Path(root).expanduser().resolve()
    safe_id = re.sub(r"[^A-Za-z0-9-]", "", profile_id)[:36]
    if not safe_id:
        raise ProfileError("Invalid profile identifier.")
    candidate = (resolved_root / safe_id).resolve()
    if resolved_root not in candidate.parents:
        raise ProfileError("Profile path escaped the configured root.")
    return candidate


def _dir_facts(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False, "size_bytes": 0, "entries": 0, "modified_at": None}
    size = 0
    entries = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                size += item.stat().st_size
                entries += 1
        except OSError:
            continue
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        modified = None
    return {"exists": True, "size_bytes": size, "entries": entries, "modified_at": modified}


def create_profile(
    db: Session,
    *,
    root: Path,
    name: str,
    label: str = "",
    agent_id: str | None = None,
    isolation: str = "per_profile",
) -> BrowserProfile:
    clean_name = validate_name(name)
    if db.scalar(select(BrowserProfile).where(BrowserProfile.name == clean_name)) is not None:
        raise ProfileError("A profile with that name already exists.")
    if agent_id is not None and db.get(Agent, agent_id) is None:
        raise ProfileError("The owning agent does not exist.")
    if isolation not in ("per_profile", "shared_readonly"):
        raise ProfileError("Isolation must be 'per_profile' or 'shared_readonly'.")

    profile = BrowserProfile(
        name=clean_name,
        label=(label or "").strip()[:LABEL_MAX],
        agent_id=agent_id,
        isolation=isolation,
        status="created",
        session_state="not_inspected",
        profile_path="",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(profile)
    db.flush()
    resolved = profile_dir(root, profile.id)
    resolved.mkdir(parents=True, exist_ok=True)
    profile.profile_path = str(resolved)
    add_event(
        db,
        "browser_profile",
        profile.id,
        "browser_profile.created",
        f"Browser profile '{profile.name}' created (empty directory; no browser launched).",
    )
    db.flush()
    return profile


def transition(db: Session, profile: BrowserProfile, *, target: str, note: str = "") -> BrowserProfile:
    if target not in STATES:
        raise ProfileError(f"State must be one of: {', '.join(STATES)}.")
    if target == profile.status:
        raise ProfileError(f"Profile is already '{profile.status}'.")
    if target not in TRANSITIONS.get(profile.status, ()):
        raise ProfileError(
            f"Transition '{profile.status}' → '{target}' is not allowed. "
            f"Allowed: {', '.join(TRANSITIONS.get(profile.status, ())) or 'none'}."
        )
    previous = profile.status
    profile.status = target
    profile.updated_at = _now()
    add_event(
        db,
        "browser_profile",
        profile.id,
        f"browser_profile.{target}",
        f"Browser profile '{profile.name}' moved {previous} → {target}" + (f": {note.strip()[:200]}" if note else "."),
    )
    db.flush()
    return profile


def lock(db: Session, profile: BrowserProfile, *, locked_by: str) -> BrowserProfile:
    """Exclusive use by one worker; a double lock is refused, not overwritten."""
    if profile.status == "locked":
        raise ProfileError(
            f"Profile is already locked by '{locked_by if not profile.locked_by else profile.locked_by}'."
        )
    if profile.status not in ("created", "ready"):
        raise ProfileError(f"A '{profile.status}' profile cannot be locked.")
    profile.locked_by = (locked_by or "").strip()[:120] or "unknown"
    profile.locked_at = _now()
    return transition(db, profile, target="locked", note=f"locked by {profile.locked_by}")


def unlock(db: Session, profile: BrowserProfile) -> BrowserProfile:
    if profile.status != "locked":
        raise ProfileError("Only a locked profile can be unlocked.")
    profile.locked_by = None
    profile.locked_at = None
    return transition(db, profile, target="ready")


def update_profile(
    db: Session,
    profile: BrowserProfile,
    *,
    label: str | None = None,
    agent_id: str | None = None,
    clear_agent: bool = False,
) -> BrowserProfile:
    if label is not None:
        profile.label = label.strip()[:LABEL_MAX]
    if clear_agent:
        profile.agent_id = None
    elif agent_id is not None:
        if db.get(Agent, agent_id) is None:
            raise ProfileError("The owning agent does not exist.")
        profile.agent_id = agent_id
    profile.updated_at = _now()
    add_event(db, "browser_profile", profile.id, "browser_profile.updated", f"Browser profile '{profile.name}' updated.")
    db.flush()
    return profile


def delete_profile(db: Session, profile: BrowserProfile, *, root: Path, confirm: bool) -> dict[str, object]:
    """Remove a profile's directory and record. Refuses without explicit confirmation."""
    if not confirm:
        raise ProfileError("Deleting a browser profile removes its stored data; pass confirm=true to proceed.")
    if profile.status == "locked":
        raise ProfileError("Unlock the profile before deleting it.")
    resolved = profile_dir(root, profile.id)
    removed_bytes = 0
    if resolved.exists():
        removed_bytes = sum(
            item.stat().st_size for item in resolved.rglob("*") if item.is_file()
        )
        shutil.rmtree(resolved)
    name = profile.name
    db.delete(profile)
    add_event(
        db,
        "browser_profile",
        None,
        "browser_profile.deleted",
        f"Browser profile '{name}' and {removed_bytes} byte(s) of stored data were deleted.",
    )
    db.flush()
    return {"deleted": True, "name": name, "removed_bytes": removed_bytes}


def profile_payload(profile: BrowserProfile, *, root: Path) -> dict[str, object]:
    facts = _dir_facts(profile_dir(root, profile.id))
    return {
        "id": profile.id,
        "name": profile.name,
        "label": profile.label,
        "agent_id": profile.agent_id,
        "isolation": profile.isolation,
        "status": profile.status,
        "locked_by": profile.locked_by,
        "locked_at": profile.locked_at.isoformat() if profile.locked_at else None,
        "session_state": profile.session_state,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        # Path is reported relative to the root, not as an absolute host path.
        "directory": f"{profile.name}/",
        **facts,
        "automation_available": False,
        "automation_reason": (
            "No browser driver is installed in this build and AATM never launches or drives a browser. "
            "Profile storage and exclusivity are real; automation is not implemented."
        ),
        "credentials_inspected": False,
        "credentials_note": "Cookies, saved logins and session storage are never read or returned.",
    }


def list_profiles(db: Session, *, root: Path, agent_id: str | None = None) -> list[dict[str, object]]:
    query = select(BrowserProfile).order_by(BrowserProfile.created_at)
    if agent_id is not None:
        query = query.where(BrowserProfile.agent_id == agent_id)
    return [profile_payload(profile, root=root) for profile in db.scalars(query).all()]


def profile_for_agent(db: Session, *, root: Path, agent_id: str) -> dict[str, object] | None:
    profile = db.scalar(
        select(BrowserProfile).where(BrowserProfile.agent_id == agent_id, BrowserProfile.status != "archived")
    )
    return profile_payload(profile, root=root) if profile is not None else None


def find_profile(db: Session, profile_id: str) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise ProfileError("Browser profile not found.")
    return profile

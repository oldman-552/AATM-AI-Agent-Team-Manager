"""Persisted, non-secret application settings.

What belongs here: UI/behaviour preferences that are safe to read back and show
in a settings page — default language, theme, page size, notification poll
interval, retention windows.

What must never belong here: API keys, tokens, passwords or credential
references. `validate_settings` rejects credential-shaped keys, and the settings
endpoint only ever returns this allow-listed shape. Provider credentials live in
`provider_configs` as `env:`/`keyring:` *references* and are never returned.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import AppSetting

SETTINGS_KEY = "user_preferences"
LANGUAGES = ("en", "ar", "fa")
THEMES = ("dark", "light")
PAGE_SIZES = (10, 20, 50, 100)

DEFAULTS: dict[str, object] = {
    "language": "en",
    "theme": "dark",
    "page_size": 20,
    "notification_poll_seconds": 30,
    "checkpoint_retention": 20,
    "backup_retention": 5,
}

FORBIDDEN_KEY_HINTS = (
    "key", "token", "secret", "password", "passwd", "credential", "auth", "dsn", "url",
)


class SettingsError(ValueError):
    """A safe, user-facing settings validation failure."""


def validate_settings(payload: dict[str, object]) -> dict[str, object]:
    """Validate an allow-listed settings payload. Unknown keys are rejected."""
    unknown = set(payload) - set(DEFAULTS)
    if unknown:
        raise SettingsError(f"Unknown setting(s): {', '.join(sorted(unknown))}.")
    for key in payload:
        if any(hint in key.lower() for hint in FORBIDDEN_KEY_HINTS):
            raise SettingsError("Credential-like setting names are not accepted; keep secrets in env:/keyring.")

    cleaned: dict[str, object] = {}
    if "language" in payload:
        if payload["language"] not in LANGUAGES:
            raise SettingsError(f"Language must be one of: {', '.join(LANGUAGES)}.")
        cleaned["language"] = payload["language"]
    if "theme" in payload:
        if payload["theme"] not in THEMES:
            raise SettingsError(f"Theme must be one of: {', '.join(THEMES)}.")
        cleaned["theme"] = payload["theme"]
    if "page_size" in payload:
        value = payload["page_size"]
        if not isinstance(value, int) or value not in PAGE_SIZES:
            raise SettingsError(f"Page size must be one of: {', '.join(map(str, PAGE_SIZES))}.")
        cleaned["page_size"] = value
    if "notification_poll_seconds" in payload:
        value = payload["notification_poll_seconds"]
        if not isinstance(value, int) or not 10 <= value <= 600:
            raise SettingsError("Notification polling must be between 10 and 600 seconds.")
        cleaned["notification_poll_seconds"] = value
    if "checkpoint_retention" in payload:
        value = payload["checkpoint_retention"]
        if not isinstance(value, int) or not 1 <= value <= 500:
            raise SettingsError("Checkpoint retention must be between 1 and 500.")
        cleaned["checkpoint_retention"] = value
    if "backup_retention" in payload:
        value = payload["backup_retention"]
        if not isinstance(value, int) or not 1 <= value <= 100:
            raise SettingsError("Backup retention must be between 1 and 100.")
        cleaned["backup_retention"] = value
    return cleaned


def read_settings(db: Session) -> dict[str, object]:
    row = db.get(AppSetting, SETTINGS_KEY)
    stored = dict(row.value or {}) if row else {}
    merged = {**DEFAULTS, **{key: value for key, value in stored.items() if key in DEFAULTS}}
    merged["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    return merged


def write_settings(db: Session, payload: dict[str, object], *, updated_by: str = "local-user") -> dict[str, object]:
    cleaned = validate_settings(payload)
    row = db.get(AppSetting, SETTINGS_KEY)
    current = {key: value for key, value in (row.value or {}).items() if key in DEFAULTS} if row else {}
    merged = {**DEFAULTS, **current, **cleaned}
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=merged)
        db.add(row)
    else:
        row.value = merged
        row.updated_at = datetime.now(timezone.utc)
    changed = ", ".join(sorted(cleaned)) or "no changes"
    add_event(db, "settings", "settings", "settings.updated", f"Preferences updated by {updated_by}: {changed}.")
    db.flush()
    return read_settings(db)


def reset_settings(db: Session, *, updated_by: str = "local-user") -> dict[str, object]:
    row = db.get(AppSetting, SETTINGS_KEY)
    if row is not None:
        row.value = dict(DEFAULTS)
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(AppSetting(key=SETTINGS_KEY, value=dict(DEFAULTS)))
    add_event(db, "settings", "settings", "settings.reset", f"Preferences reset to defaults by {updated_by}.")
    db.flush()
    return read_settings(db)


def retention_targets(db: Session) -> dict[str, int]:
    """Expose the retention values so a maintenance command can read them."""
    settings = read_settings(db)
    return {
        "checkpoint_retention": int(settings["checkpoint_retention"]),  # type: ignore[arg-type]
        "backup_retention": int(settings["backup_retention"]),  # type: ignore[arg-type]
    }


def export_settings(db: Session) -> dict[str, object]:
    """Settings export for backup: non-secret only, by construction."""
    return {"settings": read_settings(db), "exported_keys": sorted(DEFAULTS)}

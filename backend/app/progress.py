"""Atomic, secret-aware progress reporting used by the development watchdog."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterator

_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|cookie|private[_-]?token)\b(\s*[:=]\s*)([^\s,;]+)"
)


def sanitize(value: str) -> str:
    """Redact common credential formats and control newlines in progress fields."""
    value = value.replace("\r", " ").replace("\n", " ").replace("\x00", " ")
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value).strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace_status_field(contents: str, label: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(label)}:\r?\n[^\r\n]*")
    replacement = f"{label}:\n{value}"
    if pattern.search(contents):
        return pattern.sub(replacement, contents, count=1)
    return contents


def _read_state(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_state(path: Path, state: dict[str, object]) -> None:
    _atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def record_event(
    root: Path,
    *,
    phase: str,
    task: str,
    action: str,
    activity: str,
    files_created: list[str] | None = None,
    files_modified: list[str] | None = None,
    tests: str = "Not run",
    results: str = "",
    problems: str = "None",
    solutions: str = "None",
    project_status: str = "Developing",
    now: datetime | None = None,
) -> str:
    """Append one progress event and atomically update the live status/state."""
    timestamp = format_timestamp(now)
    phase, task, action, activity = map(sanitize, (phase, task, action, activity))
    tests, results = sanitize(tests), sanitize(results)
    problems, solutions = sanitize(problems), sanitize(solutions)
    created = [sanitize(item) for item in (files_created or [])]
    modified = [sanitize(item) for item in (files_modified or [])]
    root = root.resolve()
    lock_path = root / ".aatm" / "progress.lock"
    status_path = root / "STATUS.txt"
    log_path = root / "PROGRESS_LOG.txt"
    state_path = root / ".aatm" / "progress_state.json"

    with _exclusive_lock(lock_path):
        state = _read_state(state_path)
        state.update({
            "last_activity": (now or utc_now()).astimezone(timezone.utc).isoformat(),
            "last_event": timestamp,
            "phase": phase,
            "task": task,
            "activity": activity,
            "project_status": sanitize(project_status),
        })
        _write_state(state_path, state)

        if status_path.exists():
            status_text = status_path.read_text(encoding="utf-8")
            status_text = _replace_status_field(status_text, "Last Updated", timestamp)
            status_text = _replace_status_field(status_text, "Overall Project Status", sanitize(project_status))
            status_text = _replace_status_field(status_text, "Current Phase", phase)
            status_text = _replace_status_field(status_text, "Current Task", task)
            status_text = _replace_status_field(status_text, "Current Activity", activity)
            _atomic_write(status_path, status_text)

        entry = (
            f"\n[{timestamp}] {phase} — {task}\n"
            f"Task: {task}\n"
            f"Action performed: {action}\n"
            f"Files created: {', '.join(created) if created else 'None'}\n"
            f"Files modified: {', '.join(modified) if modified else 'None'}\n"
            f"Tests executed: {tests}\n"
            f"Results: {results or 'Not recorded'}\n"
            f"Problems: {problems}\n"
            f"Solutions: {solutions}\n"
        )
        previous_log = log_path.read_text(encoding="utf-8") if log_path.exists() else "AATM DEVELOPMENT HISTORY\n========================\n"
        _atomic_write(log_path, previous_log.rstrip() + "\n" + entry)
    return timestamp


def heartbeat_once(root: Path, *, idle_after_seconds: int = 300, now: datetime | None = None) -> str:
    """Update the status timestamp and honestly label recent/idle event state."""
    current = (now or utc_now()).astimezone(timezone.utc)
    timestamp = format_timestamp(current)
    root = root.resolve()
    lock_path = root / ".aatm" / "progress.lock"
    status_path = root / "STATUS.txt"
    state_path = root / ".aatm" / "progress_state.json"
    if not status_path.exists():
        raise FileNotFoundError(f"Progress status file not found: {status_path}")

    with _exclusive_lock(lock_path):
        state = _read_state(state_path)
        last_activity_raw = state.get("last_activity")
        detail = "No work event has been recorded; heartbeat does not imply active work."
        if isinstance(last_activity_raw, str):
            try:
                last_activity = datetime.fromisoformat(last_activity_raw)
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                age = max(0, int((current - last_activity.astimezone(timezone.utc)).total_seconds()))
                last_event_time = str(state.get("last_event", "timestamp unavailable"))
                last_event = sanitize(str(state.get("activity", "")))
                if age >= idle_after_seconds:
                    detail = f"Idle — last work event was {age // 60} minute(s) ago, at {last_event_time} ({last_event}); no new progress is claimed."
                else:
                    detail = f"Last work event at {last_event_time} ({last_event}); heartbeat records time only and claims no new work."
            except ValueError:
                detail = "Last work-event timestamp is invalid; heartbeat does not imply active work."

        status_text = status_path.read_text(encoding="utf-8")
        status_text = _replace_status_field(status_text, "Last Updated", timestamp)
        status_text = _replace_status_field(status_text, "Current Activity", sanitize(detail))
        _atomic_write(status_path, status_text)
        state["last_heartbeat"] = current.isoformat()
        _write_state(state_path, state)
    return detail


def run_heartbeat(root: Path, *, interval_seconds: int = 300, idle_after_seconds: int = 300) -> None:
    """Run the five-minute progress heartbeat until interrupted."""
    if interval_seconds < 1:
        raise ValueError("Heartbeat interval must be at least one second.")
    heartbeat_once(root, idle_after_seconds=idle_after_seconds)
    import time

    while True:
        time.sleep(interval_seconds)
        heartbeat_once(root, idle_after_seconds=idle_after_seconds)

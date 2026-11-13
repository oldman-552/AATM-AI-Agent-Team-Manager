from datetime import datetime, timedelta, timezone
import json

from app.progress import heartbeat_once, record_event


STATUS_TEMPLATE = """==================================================
AATM — LIVE DEVELOPMENT STATUS
==================================================

Last Updated:
2026-11-13 00:00 UTC

Overall Project Status:
Developing

Current Phase:
Phase 1 — Foundation

Current Task:
Original task

Current Activity:
Original activity

==================================================
"""


def create_progress_root(root) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "STATUS.txt").write_text(STATUS_TEMPLATE, encoding="utf-8")
    (root / "PROGRESS_LOG.txt").write_text("Existing historical event\n", encoding="utf-8")


def test_event_updates_status_appends_history_and_redacts_secrets(tmp_path) -> None:
    create_progress_root(tmp_path)
    now = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)

    record_event(
        tmp_path,
        phase="Phase 1 — Foundation",
        task="Write API",
        action="Added routes",
        activity="Validated API_KEY=super-secret locally",
        files_created=["backend/app/api.py"],
        tests="5 passed",
        results="Success",
        now=now,
    )

    status = (tmp_path / "STATUS.txt").read_text(encoding="utf-8")
    log = (tmp_path / "PROGRESS_LOG.txt").read_text(encoding="utf-8")
    state = json.loads((tmp_path / ".aatm" / "progress_state.json").read_text(encoding="utf-8"))
    assert "2026-11-13 10:00 UTC" in status
    assert "Validated API_KEY=[REDACTED] locally" in status
    assert "Added routes" in log
    assert "Existing historical event" in log
    assert "5 passed" in log
    assert "super-secret" not in status + log + json.dumps(state)
    assert "[REDACTED]" in status


def test_heartbeat_marks_stale_activity_idle_without_inventing_progress(tmp_path) -> None:
    create_progress_root(tmp_path)
    last_event = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    now = last_event + timedelta(minutes=7)
    record_event(
        tmp_path,
        phase="Phase 1",
        task="Test heartbeat",
        action="Recorded a test event",
        activity="Unit test activity",
        now=last_event,
    )

    detail = heartbeat_once(tmp_path, idle_after_seconds=300, now=now)
    status = (tmp_path / "STATUS.txt").read_text(encoding="utf-8")
    assert detail.startswith("Idle —")
    assert "no new progress is claimed" in status
    assert "2026-11-13 09:07 UTC" in status
    assert "Unit test activity" in status

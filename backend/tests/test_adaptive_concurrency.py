"""The adaptive dispatch cap is explicit opt-in, bounded, and fail-safe."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Task
from app.resources import ResourceSnapshot


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app("sqlite://", allowed_hosts=["testserver"])) as tc:
        yield tc


def pressured_snapshot(**overrides) -> ResourceSnapshot:
    values = {
        "cpu_percent": 95.0,
        "load_average_1m": 8.0,
        "cpu_count": 4,
        "memory_total_mb": 8000.0,
        "memory_available_mb": 400.0,
        "memory_used_ratio": 0.95,
        "disk_total_gb": 100.0,
        "disk_free_gb": 2.0,
        "disk_used_ratio": 0.98,
        "measured_at": "2026-11-13T00:00:00+00:00",
    }
    values.update(overrides)
    return ResourceSnapshot(**values)


def test_adaptation_is_disabled_by_default_and_keeps_configured_cap(client, monkeypatch):
    from app.adaptive_concurrency import concurrency_policy

    monkeypatch.delenv("AATM_ADAPTIVE_CONCURRENCY", raising=False)
    monkeypatch.setenv("AATM_MAX_CONCURRENCY", "4")
    with Session(client.app.state.engine) as db:
        policy = concurrency_policy(db)
    assert policy["adaptive_enabled"] is False
    assert policy["configured_max"] == 4
    assert policy["effective_dispatch_budget"] == 4
    assert policy["recommended_max"] is None
    assert policy["applied_automatically"] is False


def test_adaptation_only_reduces_the_configured_cap(client, monkeypatch):
    from app.adaptive_concurrency import concurrency_policy

    monkeypatch.setenv("AATM_ADAPTIVE_CONCURRENCY", "yes")
    monkeypatch.setenv("AATM_MAX_CONCURRENCY", "4")
    monkeypatch.setattr("app.adaptive_concurrency.sample_resources", lambda _path: pressured_snapshot())
    with Session(client.app.state.engine) as db:
        policy = concurrency_policy(db, for_run=True)
    assert policy["adaptive_enabled"] is True
    assert policy["configured_max"] == 4
    assert policy["recommended_max"] == 1
    assert policy["effective_dispatch_budget"] == 1
    assert policy["applied_automatically"] is True
    assert policy["snapshot"]["memory_used_ratio"] == 0.95


def test_adaptive_policy_subtracts_running_tasks_and_can_close_dispatch(client, monkeypatch):
    from app.adaptive_concurrency import concurrency_policy

    monkeypatch.setenv("AATM_ADAPTIVE_CONCURRENCY", "1")
    monkeypatch.setenv("AATM_MAX_CONCURRENCY", "4")
    monkeypatch.setattr("app.adaptive_concurrency.sample_resources", lambda _path: pressured_snapshot())
    with Session(client.app.state.engine) as db:
        db.add(Task(title="Existing run", state="running"))
        db.commit()
        policy = concurrency_policy(db)
    assert policy["in_flight"] == 1
    assert policy["recommended_max"] == 1
    assert policy["effective_dispatch_budget"] == 0


def test_invalid_operator_cap_fails_closed_to_one(client, monkeypatch):
    from app.adaptive_concurrency import configured_max_concurrency

    for value in ("invalid", "0", "21", "-1"):
        monkeypatch.setenv("AATM_MAX_CONCURRENCY", value)
        assert configured_max_concurrency() == 1


def test_adaptive_controls_load_from_dotenv_and_invalid_values_fail_closed(tmp_path, monkeypatch):
    from app.adaptive_concurrency import adaptive_concurrency_enabled, configured_max_concurrency
    from app.core.config import Settings

    dotenv = tmp_path / ".env"
    dotenv.write_text("AATM_ADAPTIVE_CONCURRENCY=true\nAATM_MAX_CONCURRENCY=6\n", encoding="utf-8")
    config = Settings(_env_file=dotenv)
    monkeypatch.setattr("app.adaptive_concurrency.settings", config)
    monkeypatch.delenv("AATM_ADAPTIVE_CONCURRENCY", raising=False)
    monkeypatch.delenv("AATM_MAX_CONCURRENCY", raising=False)
    assert adaptive_concurrency_enabled() is True
    assert configured_max_concurrency() == 6

    invalid = tmp_path / "bad.env"
    invalid.write_text("AATM_ADAPTIVE_CONCURRENCY=yes\nAATM_MAX_CONCURRENCY=oops\n", encoding="utf-8")
    monkeypatch.setattr("app.adaptive_concurrency.settings", Settings(_env_file=invalid))
    assert adaptive_concurrency_enabled() is True
    assert configured_max_concurrency() == 1


def test_orchestrator_status_reports_adaptive_mode(client, monkeypatch):
    monkeypatch.delenv("AATM_ADAPTIVE_CONCURRENCY", raising=False)
    body = client.get("/api/v1/orchestrator/status").json()
    assert body["concurrency"]["adaptive_enabled"] is False
    assert body["concurrency"]["effective_dispatch_budget"] == 1

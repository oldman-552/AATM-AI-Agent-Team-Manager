"""Local resource telemetry and bounded concurrency recommendations."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.resources import ResourceSnapshot, recommend_concurrency, sample_resources


def snapshot(**overrides) -> ResourceSnapshot:
    base = dict(
        cpu_percent=20.0,
        load_average_1m=0.4,
        cpu_count=4,
        memory_total_mb=8000.0,
        memory_available_mb=6000.0,
        memory_used_ratio=0.25,
        disk_total_gb=100.0,
        disk_free_gb=60.0,
        disk_used_ratio=0.4,
        measured_at="2026-11-13T00:00:00+00:00",
    )
    base.update(overrides)
    return ResourceSnapshot(**base)


def test_recommendation_is_bounded_and_advisory() -> None:
    result = recommend_concurrency(snapshot(), configured_max=10)
    assert result["recommended_concurrency"] == 4  # capped by CPU ceiling, not 10
    assert result["applied_automatically"] is False
    assert "advis" in str(result["note"]).lower() or "recommendation" in str(result["note"]).lower()

    assert recommend_concurrency(snapshot(cpu_count=1), configured_max=8)["recommended_concurrency"] == 1


def test_memory_and_disk_pressure_force_the_floor() -> None:
    memory = recommend_concurrency(snapshot(memory_used_ratio=0.95), configured_max=4)
    assert memory["recommended_concurrency"] == 1
    assert any("Memory pressure" in reason for reason in memory["reasons"])

    disk = recommend_concurrency(snapshot(disk_used_ratio=0.99), configured_max=4)
    assert disk["recommended_concurrency"] == 1
    assert any("Disk pressure" in reason for reason in disk["reasons"])


def test_high_load_halves_the_recommendation() -> None:
    result = recommend_concurrency(snapshot(load_average_1m=6.0, cpu_count=4), configured_max=4)
    assert result["recommended_concurrency"] == 2
    assert any("halved" in reason for reason in result["reasons"])


def test_in_flight_is_reported_without_changing_configuration() -> None:
    result = recommend_concurrency(snapshot(), configured_max=2, in_flight=2)
    assert result["in_flight"] == 2
    assert result["configured_max"] == 2
    assert any("in flight" in reason for reason in result["reasons"])


def test_sample_returns_local_measurements_without_network() -> None:
    sample = sample_resources()
    payload = sample.as_dict()
    assert payload["cpu_count"] >= 1
    assert payload["measured_at"]
    assert payload["disk_total_gb"] is None or payload["disk_total_gb"] > 0
    if payload["memory_used_ratio"] is not None:
        assert 0.0 <= payload["memory_used_ratio"] <= 1.0


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app("sqlite://", allowed_hosts=["testserver"])) as tc:
        yield tc


def test_resources_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/system/resources", params={"configured_max": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["cpu_count"] >= 1
    assert 1 <= body["recommendation"]["recommended_concurrency"] <= 3
    assert body["recommendation"]["applied_automatically"] is False
    assert "locally" in body["telemetry"]
    assert client.get("/api/v1/system/resources", params={"configured_max": 0}).status_code == 422

"""API tests for provider configuration, budgets, usage and offline routing."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SECRET = "sk-ant-should-never-appear-9988"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AATM_TEST_KEY", SECRET)
    app = create_app(
        "sqlite://",
        allowed_origins=["http://localhost:5173"],
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
    )
    with TestClient(app) as test_client:
        yield test_client


def test_catalog_is_offline_and_contains_no_secret_values(client: TestClient) -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.text
    assert SECRET not in body
    payload = response.json()
    assert payload["live_requests_allowed"] is False
    assert [item["id"] for item in payload["providers"]] == ["arena_bridge", "anthropic"]
    arena = payload["providers"][0]
    assert arena["health"]["state"] == "blocked"
    assert arena["config"]["enabled"] is False
    assert arena["health"]["live_calls_enabled"] is False
    assert any("CAPTCHA" in reason for reason in arena["health"]["reasons"])
    assert payload["settings"]["routing_policy"] == "arena_first"
    assert "not confirmed provider billing" in payload["pricing"]["basis"]


def test_raw_credentials_are_rejected_and_references_are_safe(client: TestClient) -> None:
    raw = client.patch("/api/v1/providers/anthropic/config", json={"api_key": SECRET})
    assert raw.status_code == 422  # extra fields are forbidden

    raw_ref = client.patch("/api/v1/providers/anthropic/config", json={"credential_ref": SECRET})
    assert raw_ref.status_code == 422

    accepted = client.patch(
        "/api/v1/providers/anthropic/config",
        json={"credential_ref": "env:AATM_TEST_KEY", "enabled": True, "model": "test-model"},
    )
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["config"]["credential"]["reference"] == "env:AATM_TEST_KEY"
    assert payload["config"]["live_requests_allowed"] is False
    assert SECRET not in str(payload)
    assert payload["health"]["credential_available"] is True
    assert payload["health"]["live_calls_enabled"] is False

    cleared = client.patch(
        "/api/v1/providers/anthropic/config", json={"clear_credential": True}
    )
    assert cleared.status_code == 200
    assert cleared.json()["config"]["credential"] is None
    assert cleared.json()["health"]["credential_available"] is False

    conflict = client.patch(
        "/api/v1/providers/anthropic/config",
        json={"clear_credential": True, "credential_ref": "env:AATM_TEST_KEY"},
    )
    assert conflict.status_code == 422


def test_arena_provider_cannot_be_enabled(client: TestClient) -> None:
    response = client.patch("/api/v1/providers/arena_bridge/config", json={"enabled": True})
    assert response.status_code == 409
    health = client.get("/api/v1/providers/arena_bridge/health").json()
    assert health["state"] == "blocked"
    assert health["enabled"] is False


def test_budgets_and_routing_are_dry_runs_without_usage(client: TestClient) -> None:
    initial = client.post("/api/v1/providers/route", json={"paid_consent": True}).json()
    assert initial["status"] == "no_eligible_provider"
    assert initial["execution_performed"] is False

    configured = client.patch(
        "/api/v1/providers/anthropic/config",
        json={"enabled": True, "model": "test-model", "credential_ref": "env:AATM_TEST_KEY"},
    )
    assert configured.status_code == 200

    no_budget = client.post("/api/v1/providers/route", json={"paid_consent": True}).json()
    assert no_budget["status"] == "no_eligible_provider"
    assert any("budget" in reason.lower() for reason in no_budget["reasons"])

    budget = client.put(
        "/api/v1/budgets",
        json={"scope": "daily", "provider_id": "anthropic", "limit_usd": 0.5},
    )
    assert budget.status_code == 200
    assert budget.json()["limit"]["limit_usd"] == 0.5

    selected = client.post(
        "/api/v1/providers/route",
        json={
            "paid_consent": True,
            "estimated_input_tokens": 1000,
            "estimated_output_tokens": 1024,
            "complexity": "high",
        },
    )
    assert selected.status_code == 200
    decision = selected.json()
    assert decision["status"] == "selected"
    assert decision["provider_id"] == "anthropic"
    assert decision["execution_performed"] is False
    assert decision["budget"]["allowed"] is True
    assert decision["cost"]["billing_status"] == "estimated"

    usage = client.get("/api/v1/usage").json()
    assert usage["total_records"] == 0  # routing never records usage or spends money
    assert SECRET not in str(usage)

    without_consent = client.post("/api/v1/providers/route", json={"paid_consent": False}).json()
    assert without_consent["status"] == "no_eligible_provider"
    assert any("consent" in reason.lower() for reason in without_consent["reasons"])

    zero = client.put(
        "/api/v1/budgets",
        json={"scope": "daily", "provider_id": "anthropic", "limit_usd": 0},
    )
    assert zero.status_code == 200
    denied = client.post("/api/v1/providers/route", json={"paid_consent": True}).json()
    assert denied["status"] == "no_eligible_provider"


def test_settings_validation_and_no_execution_route(client: TestClient) -> None:
    updated = client.patch("/api/v1/providers/settings", json={"routing_policy": "claude_first"})
    assert updated.status_code == 200
    assert updated.json()["routing_policy"] == "claude_first"
    assert updated.json()["live_requests_allowed"] is False

    assert client.patch("/api/v1/providers/settings", json={"routing_policy": "anything"}).status_code == 422
    assert client.patch(
        "/api/v1/providers/settings", json={"user_defined_order": ["unknown"]}
    ).status_code == 422
    assert client.patch("/api/v1/providers/anthropic/config", json={"apiKey": SECRET}).status_code == 422

    execution = client.post("/api/v1/providers/anthropic/execute", json={})
    assert execution.status_code in (404, 405)  # no live execution is exposed

    assert client.post("/api/v1/providers/route", json={"preferred_provider": "unknown"}).status_code == 422
    assert client.post("/api/v1/providers/route", json={"agent_id": "missing"}).status_code == 404


def test_untrusted_host_and_origin_are_rejected(client: TestClient) -> None:
    hostile = client.get("/api/v1/providers", headers={"host": "attacker.invalid"})
    assert hostile.status_code == 400
    preflight = client.options(
        "/api/v1/providers",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "PATCH",
        },
    )
    assert "access-control-allow-origin" not in {key.lower() for key in preflight.headers}

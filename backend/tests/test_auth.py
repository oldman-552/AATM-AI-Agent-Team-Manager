"""Local authentication and cross-origin mutation protection."""

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthConfig
from app.main import create_app

TOKEN = "test-local-token-abcdef123456"


@pytest.fixture
def open_client() -> TestClient:
    with TestClient(create_app("sqlite://", allowed_hosts=["testserver"], allowed_origins=["http://localhost:5173"])) as tc:
        yield tc


@pytest.fixture
def token_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AATM_AUTH_MODE", "token")
    monkeypatch.setenv("AATM_AUTH_TOKEN", TOKEN)
    with TestClient(create_app("sqlite://", allowed_hosts=["testserver"], allowed_origins=["http://localhost:5173"])) as tc:
        yield tc


def test_token_mode_requires_a_bearer_token(token_client: TestClient) -> None:
    assert token_client.get("/api/v1/health").status_code == 200  # health stays public
    unauthorized = token_client.get("/api/v1/projects")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    bad = token_client.get("/api/v1/projects", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401

    ok = token_client.get("/api/v1/projects", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200

    created = token_client.post(
        "/api/v1/projects",
        json={"name": "Authorized project"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert created.status_code == 201


def test_token_mode_rejects_non_bearer_schemes(token_client: TestClient) -> None:
    for header in ("Basic abc", TOKEN, "Bearer ", ""):
        response = token_client.get("/api/v1/projects", headers={"Authorization": header})
        assert response.status_code == 401


def test_token_mode_never_echoes_the_token(token_client: TestClient) -> None:
    response = token_client.get("/api/v1/projects", headers={"Authorization": "Bearer wrong-token"})
    assert "wrong-token" not in response.text
    assert TOKEN not in response.text


def test_missing_token_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("AATM_AUTH_MODE", "token")
    monkeypatch.delenv("AATM_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="requires AATM_AUTH_TOKEN"):
        AuthConfig.from_settings(["http://localhost:5173"])


def test_unknown_auth_mode_falls_back_to_off(monkeypatch) -> None:
    monkeypatch.setenv("AATM_AUTH_MODE", "custom-nonsense")
    config = AuthConfig.from_settings()
    assert config.mode == "off"
    assert config.enabled is False


def test_cross_origin_mutations_are_rejected_even_without_token_mode(open_client: TestClient) -> None:
    # Same-origin/no-Origin requests keep working for local tooling.
    assert open_client.post("/api/v1/projects", json={"name": "Local"}).status_code == 201

    hostile = open_client.post(
        "/api/v1/projects",
        json={"name": "CSRF"},
        headers={"Origin": "https://evil.example"},
    )
    assert hostile.status_code == 403
    assert "Cross-origin" in hostile.json()["detail"]

    allowed = open_client.post(
        "/api/v1/projects",
        json={"name": "Allowed origin"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert allowed.status_code == 201


def test_cross_origin_reads_are_still_allowed(open_client: TestClient) -> None:
    response = open_client.get("/api/v1/projects", headers={"Origin": "https://evil.example"})
    # CORS headers are absent for hostile origins, but the read itself is not a state change.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


def test_token_mode_also_blocks_hostile_origin(token_client: TestClient) -> None:
    response = token_client.post(
        "/api/v1/projects",
        json={"name": "x"},
        headers={"Origin": "https://evil.example", "Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 403

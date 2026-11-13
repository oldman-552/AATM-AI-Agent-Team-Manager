"""Browser profiles: real isolation and exclusivity, zero fake automation."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AATM_BROWSER_PROFILES_ROOT", str(tmp_path / "profiles"))
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def create_profile(client: TestClient, name: str = "chrome-work", **extra) -> dict:
    response = client.post("/api/v1/browser-profiles", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()["profile"]


def test_profile_creates_a_real_isolated_directory(client: TestClient, tmp_path) -> None:
    profile = create_profile(client)
    assert profile["status"] == "created"
    assert profile["exists"] is True
    assert profile["entries"] == 0
    # The directory lives under the configured root and is not the root itself.
    directory = tmp_path / "profiles" / profile["id"]
    assert directory.is_dir()

    second = create_profile(client, name="chrome-personal")
    assert second["id"] != profile["id"]
    assert directory != tmp_path / "profiles" / second["id"]


def test_profiles_never_claim_automation_or_inspect_credentials(client: TestClient) -> None:
    profile = create_profile(client)
    assert profile["automation_available"] is False
    assert "never launches or drives a browser" in profile["automation_reason"]
    assert profile["credentials_inspected"] is False
    assert profile["session_state"] == "not_inspected"
    listing = client.get("/api/v1/browser-profiles").json()
    assert listing["automation_available"] is False
    # No *field* may leak cookie/login material. (The explanatory note legitimately
    # mentions cookies in order to say they are never read.)
    profile_keys = set(listing["profiles"][0])
    for forbidden in ("cookies", "password", "token", "tokens", "storage_state", "localstorage", "jwt"):
        assert forbidden not in profile_keys
    assert {"credentials_inspected", "session_state"} <= profile_keys


def test_names_are_validated_and_unique(client: TestClient) -> None:
    create_profile(client, name="chrome-work")
    for bad in ("../escape", "a/b", "", "..", "x" * 61):
        assert client.post("/api/v1/browser-profiles", json={"name": bad}).status_code == 422, bad
    duplicate = client.post("/api/v1/browser-profiles", json={"name": "chrome-work"})
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.json()["detail"]


def test_lock_is_exclusive(client: TestClient) -> None:
    profile = create_profile(client)
    first = client.post(f"/api/v1/browser-profiles/{profile['id']}/lock", json={"locked_by": "worker-a"})
    assert first.status_code == 200
    assert first.json()["profile"]["status"] == "locked"
    assert first.json()["profile"]["locked_by"] == "worker-a"

    second = client.post(f"/api/v1/browser-profiles/{profile['id']}/lock", json={"locked_by": "worker-b"})
    assert second.status_code == 409
    assert "already locked" in second.json()["detail"]

    # A locked profile cannot be deleted until it is unlocked.
    assert client.delete(f"/api/v1/browser-profiles/{profile['id']}", params={"confirm": True}).status_code == 409
    unlocked = client.post(f"/api/v1/browser-profiles/{profile['id']}/unlock")
    assert unlocked.json()["profile"]["status"] == "ready"
    assert unlocked.json()["profile"]["locked_by"] is None
    assert client.post(f"/api/v1/browser-profiles/{profile['id']}/unlock").status_code == 409


def test_state_transitions_are_validated(client: TestClient) -> None:
    profile = create_profile(client)
    archived = client.patch(f"/api/v1/browser-profiles/{profile['id']}/state", json={"target_state": "archived"})
    assert archived.json()["profile"]["status"] == "archived"
    # Archived is terminal.
    assert client.patch(
        f"/api/v1/browser-profiles/{profile['id']}/state", json={"target_state": "ready"}
    ).status_code == 409
    fresh = create_profile(client, name="second")
    assert client.patch(
        f"/api/v1/browser-profiles/{fresh['id']}/state", json={"target_state": "exploded"}
    ).status_code == 409


def test_agent_assignment_and_validation(client: TestClient) -> None:
    agent = client.post("/api/v1/agents", json={"name": "Browser worker", "role": "developer"}).json()
    profile = create_profile(client, agent_id=agent["id"])
    assert profile["agent_id"] == agent["id"]

    assert client.post("/api/v1/browser-profiles", json={"name": "bad", "agent_id": "missing"}).status_code == 404
    assert client.patch(
        f"/api/v1/browser-profiles/{profile['id']}", json={"agent_id": "missing"}
    ).status_code == 422

    updated = client.patch(f"/api/v1/browser-profiles/{profile['id']}", json={"label": "Work profile"})
    assert updated.json()["profile"]["label"] == "Work profile"
    cleared = client.patch(f"/api/v1/browser-profiles/{profile['id']}", json={"clear_agent": True})
    assert cleared.json()["profile"]["agent_id"] is None


def test_delete_requires_confirmation_and_removes_data(client: TestClient, tmp_path) -> None:
    profile = create_profile(client)
    directory = tmp_path / "profiles" / profile["id"]
    (directory / "Preferences").write_bytes(b"x" * 1000)

    refused = client.delete(f"/api/v1/browser-profiles/{profile['id']}")
    assert refused.status_code == 422
    assert "confirm=true" in refused.json()["detail"]
    assert directory.exists()

    deleted = client.delete(f"/api/v1/browser-profiles/{profile['id']}", params={"confirm": True}).json()
    assert deleted["deleted"] is True
    assert deleted["removed_bytes"] == 1000
    assert not directory.exists()
    assert client.get(f"/api/v1/browser-profiles/{profile['id']}").status_code == 404

    events = [event["event_type"] for event in client.get("/api/v1/events").json()]
    assert "browser_profile.deleted" in events


def test_size_accounting_reflects_files(client: TestClient, tmp_path) -> None:
    profile = create_profile(client)
    directory = tmp_path / "profiles" / profile["id"]
    (directory / "Cookies").write_bytes(b"y" * 2048)
    (directory / "sub").mkdir()
    (directory / "sub" / "blob").write_bytes(b"z" * 52)
    shown = client.get(f"/api/v1/browser-profiles/{profile['id']}").json()["profile"]
    assert shown["entries"] == 2
    assert shown["size_bytes"] == 2100

"""Preference settings: validation, persistence, and hard rejection of secrets."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def test_defaults_are_returned_before_any_change(client: TestClient) -> None:
    body = client.get("/api/v1/settings").json()
    assert body["settings"]["language"] == "en"
    assert body["settings"]["theme"] == "dark"
    assert body["settings"]["page_size"] == 20
    assert body["settings"]["updated_at"] is None
    assert "env:/keyring" in body["note"]


def test_updates_persist_and_merge(client: TestClient) -> None:
    first = client.patch("/api/v1/settings", json={"language": "ar", "theme": "light"})
    assert first.status_code == 200
    assert first.json()["settings"]["language"] == "ar"
    assert first.json()["settings"]["theme"] == "light"
    assert first.json()["settings"]["page_size"] == 20  # untouched default preserved

    second = client.patch("/api/v1/settings", json={"page_size": 50})
    assert second.json()["settings"]["language"] == "ar"  # earlier change preserved
    assert second.json()["settings"]["page_size"] == 50

    url = client.app.state.engine.url.render_as_string(hide_password=False)
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as restarted:
        body = restarted.get("/api/v1/settings").json()["settings"]
        assert body["language"] == "ar"
        assert body["page_size"] == 50
        assert body["updated_at"] is not None


def test_secret_and_unknown_settings_are_rejected(client: TestClient) -> None:
    for payload in (
        {"api_key": "sk-abc"},
        {"auth_token": "x"},
        {"password": "hunter2"},
        {"language": "ar", "unknown_pref": 1},
    ):
        response = client.patch("/api/v1/settings", json=payload)
        assert response.status_code == 422, payload
    body = client.get("/api/v1/settings").json()["settings"]
    assert body["language"] == "en"


def test_value_bounds(client: TestClient) -> None:
    bad = [
        {"language": "fr"},
        {"theme": "neon"},
        {"page_size": 7},
        {"notification_poll_seconds": 5},
        {"checkpoint_retention": 0},
        {"backup_retention": 101},
    ]
    for payload in bad:
        assert client.patch("/api/v1/settings", json=payload).status_code == 422, payload
    assert client.patch("/api/v1/settings", json={}).status_code == 422


def test_reset_and_export(client: TestClient) -> None:
    client.patch("/api/v1/settings", json={"language": "fa", "backup_retention": 9})
    reset = client.post("/api/v1/settings/reset").json()["settings"]
    assert reset["language"] == "en"
    assert reset["backup_retention"] == 5

    exported = client.get("/api/v1/settings/export").json()
    assert set(exported["settings"]) >= {"language", "theme", "page_size"}
    for forbidden in ("api_key", "token", "password", "secret"):
        assert forbidden not in exported["settings"]


def test_changes_are_audited_without_values(client: TestClient) -> None:
    client.patch("/api/v1/settings", json={"language": "ar", "updated_by": "owner"})
    events = client.get("/api/v1/events").json()
    matching = [event for event in events if event["event_type"] == "settings.updated"]
    assert matching
    assert "owner" in matching[0]["summary"]
    assert "ar" not in matching[0]["summary"] or "language" in matching[0]["summary"]

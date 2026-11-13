"""Tests for the audit event stream.

The interesting failure modes for a stream are not "does it return 200" but
"does a reconnecting client lose or repeat events", "does it ever terminate",
and "does it keep using a database session that the request already closed".
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.events import MAX_BATCH, MAX_STREAM_SECONDS, current_cursor, fetch_after, stream_from
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


@pytest.fixture
def db_session(tmp_path):
    """A live session against the same database shape the app uses."""
    from app.db import build_engine, make_session_factory

    engine = build_engine(f"sqlite:///{(tmp_path / 'direct.sqlite3').as_posix()}")
    from app.models import Base

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        yield session


def parse_frames(text: str) -> list[dict[str, object]]:
    """Turn raw SSE text into [{event, data, id}] — one dict per frame."""
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        frame: dict[str, object] = {}
        for line in block.splitlines():
            if line.startswith(":"):
                continue
            field, _, value = line.partition(": ")
            if field == "data":
                frame["data"] = json.loads(value)
            elif field in {"event", "id"}:
                frame[field] = value
        frames.append(frame)
    return frames


def test_stream_opens_with_an_honest_hello(client: TestClient):
    """The transport must describe itself truthfully as polling, not push."""
    with client.stream("GET", "/api/v1/events/stream?max_seconds=2&poll_seconds=0.25") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"].startswith("no-cache")
        for line in response.iter_lines():
            if line.startswith("data: "):
                hello = json.loads(line[len("data: "):])
                break
        else:  # pragma: no cover - the hello frame is sent unconditionally
            pytest.fail("stream produced no data frame")

    assert hello["delivery"] == "poll"
    assert hello["source"] == "audit_events table, polled"
    assert "not pushed by a broker" in hello["note"]


def test_new_events_are_delivered_and_carry_ids(client: TestClient):
    """An event recorded while the stream is open reaches the client."""
    with client.stream("GET", "/api/v1/events/stream?max_seconds=30&poll_seconds=0.25&heartbeat_seconds=5") as response:
        lines = response.iter_lines()
        # Consume the hello frame first so the stream is established.
        for line in lines:
            if line.startswith("data: "):
                break
        client.post("/api/v1/projects", json={"name": "Streamed", "description": ""})
        received = None
        for line in lines:
            if line.startswith("data: ") and '"event_type"' in line:
                received = json.loads(line[len("data: "):])
                break

    assert received is not None
    assert received["entity_type"] == "project"
    assert received["id"]


def test_resume_replays_only_what_was_missed(client: TestClient):
    """A reconnect with a cursor must not repeat it and must not skip what follows."""
    anchor = client.post("/api/v1/projects", json={"name": "Resume anchor", "description": ""}).json()
    anchor_event = next(
        event for event in client.get("/api/v1/events").json() if event["entity_id"] == anchor["id"]
    )
    later = [
        client.post("/api/v1/projects", json={"name": f"Resume later {index}", "description": ""}).json()
        for index in range(2)
    ]

    expected_ids = set()
    for project in later:
        event = next(item for item in client.get("/api/v1/events").json() if item["entity_id"] == project["id"])
        expected_ids.add(event["id"])
    assert expected_ids

    received: list[dict[str, object]] = []
    # Closing a stream waits for the generator's next yield, so a short heartbeat
    # keeps this test fast without changing what it asserts.
    with client.stream(
        "GET",
        f"/api/v1/events/stream?max_seconds=30&poll_seconds=0.25&heartbeat_seconds=5&last_event_id={anchor_event['id']}",
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data: ") and '"event_type"' in line:
                received.append(json.loads(line[len("data: "):]))
            # Stop as soon as the two expected events arrived; no need to wait for close.
            if expected_ids.issubset({str(item["id"]) for item in received}):
                break

    replayed = {str(item["id"]) for item in received}
    assert anchor_event["id"] not in replayed, "the resumed-from event must not be replayed"
    assert expected_ids.issubset(replayed), "events after the cursor must all arrive"


def test_stream_terminates_and_says_why(client: TestClient):
    """A bounded stream closes itself with a reason instead of running forever."""
    with client.stream("GET", "/api/v1/events/stream?max_seconds=2&poll_seconds=0.25") as response:
        frames = parse_frames("".join(f"{line}\n" for line in response.iter_lines()))

    assert frames[-1]["event"] == "close"
    assert frames[-1]["data"]["reason"] == "max_seconds_reached"


def test_limits_are_enforced_by_validation(client: TestClient):
    """Absurd parameters are rejected rather than accepted silently."""
    too_long = client.get(f"/api/v1/events/stream?max_seconds={MAX_STREAM_SECONDS + 1}")
    assert too_long.status_code == 422
    too_fast = client.get("/api/v1/events/stream?poll_seconds=0")
    assert too_fast.status_code == 422


def test_keyset_cursor_does_not_skip_events_sharing_a_timestamp(client: TestClient, db_session):
    """Two events with the identical timestamp must not collapse at the boundary.

    A cursor on `created_at` alone fails exactly here: the second event is neither
    "> timestamp" nor "<= timestamp" and silently disappears from every stream.
    """
    from datetime import datetime, timezone

    from app.models import AuditEvent

    stamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for suffix in ("aaa", "bbb", "ccc"):
        db_session.add(
            AuditEvent(
                id=f"fixed-{suffix}",
                entity_type="test",
                entity_id=None,
                event_type="tie",
                summary="tied timestamp",
                created_at=stamp,
            )
        )
    db_session.commit()

    first = fetch_after(db_session, None, limit=3)
    first_tied = [event for event in first if event.id.startswith("fixed-")]
    assert len(first_tied) == 3

    cursor = (first_tied[0].created_at, first_tied[0].id)
    rest = [event.id for event in fetch_after(db_session, cursor, limit=MAX_BATCH)]
    assert "fixed-bbb" in rest and "fixed-ccc" in rest
    assert "fixed-aaa" not in rest, "the cursor event itself must be excluded"


def test_generator_uses_its_own_session(client: TestClient, db_session):
    """The stream must not reuse the request session, which is closed before it runs.

    This is the classic streaming bug: the dependency's session is closed when the
    response starts, so a generator holding it fails mid-stream instead of at once.
    """
    from app.db import make_session_factory

    engine = db_session.get_bind()
    factory = make_session_factory(engine)
    frames = []
    for frame in stream_from(factory, current_cursor(db_session), poll_seconds=0.25, heartbeat_seconds=5, max_seconds=2):
        frames.append(frame)
        if len(frames) > 2:
            break
    assert frames and frames[0].startswith("event: hello")


def test_stream_requires_the_same_auth_as_everything_else(tmp_path, monkeypatch):
    """The stream must not be an unauthenticated back door.

    It is also not given a token-in-query escape hatch: URLs end up in logs and
    shell history. The dev proxy injects the bearer header server-side, which is
    what makes the browser's EventSource work without exposing a secret.
    """
    monkeypatch.setenv("AATM_AUTH_MODE", "token")
    monkeypatch.setenv("AATM_AUTH_TOKEN", "s3cret-token")
    url = f"sqlite:///{(tmp_path / 'auth.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as guarded:
        anonymous = guarded.get("/api/v1/events/stream?max_seconds=2")
        assert anonymous.status_code == 401
        assert anonymous.headers.get("www-authenticate") == "Bearer"

        # A token supplied as a query parameter must NOT be accepted.
        smuggled = guarded.get("/api/v1/events/stream?max_seconds=2&token=s3cret-token")
        assert smuggled.status_code == 401

        with guarded.stream(
            "GET",
            "/api/v1/events/stream?max_seconds=2&poll_seconds=0.25",
            headers={"Authorization": "Bearer s3cret-token"},
        ) as authorised:
            assert authorised.status_code == 200
            assert authorised.headers["content-type"].startswith("text/event-stream")

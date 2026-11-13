"""Request hardening: bounded bodies and security headers that actually appear."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.hardening import MAX_BODY_BYTES
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


def test_security_headers_are_present_on_api_and_error_responses(client: TestClient) -> None:
    for path in ("/api/v1/health", "/api/v1/projects", "/api/v1/does-not-exist"):
        response = client.get(path)
        headers = {key.lower(): value for key, value in response.headers.items()}
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert "camera=()" in headers["permissions-policy"]


def test_oversized_body_is_refused_before_validation(client: TestClient) -> None:
    payload = {"name": "big", "description": "x" * (MAX_BODY_BYTES + 10)}
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 413
    body = response.json()
    assert body["limit_bytes"] == MAX_BODY_BYTES
    assert "exceeds" in body["detail"]
    # Nothing was written.
    assert all(item["name"] != "big" for item in client.get("/api/v1/projects").json())


def test_body_just_below_the_limit_is_still_accepted(client: TestClient) -> None:
    # `description` has its own 10k cap, so the sub-limit request exercises the
    # body cap with a payload that is valid on every other axis.
    payload = {"name": "fits", "description": "x" * 9_000}
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201, response.text[:200]
    assert response.json()["name"] == "fits"
    # The cap is above every field's own limit, so no legitimate form is cut off.
    assert MAX_BODY_BYTES > 20_000


def test_understated_content_length_does_not_bypass_the_cap() -> None:
    """The cap must be enforced by counting bytes, not by trusting the header.

    httpx always sets Content-Length for an iterator body, so the streaming path
    is exercised at the ASGI layer directly, with a header that understates the
    real size.
    """
    from app.hardening import BodySizeLimitMiddleware

    async def inner(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    sent: list[dict] = []
    bodies = [b"x" * 400_000, b"x" * 400_000, b"x" * 400_000]

    async def receive():
        if bodies:
            more = len(bodies) > 1
            return {"type": "http.request", "body": bodies.pop(0), "more_body": more}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(inner, max_bytes=1_000_000)
    scope = {
        "type": "http", "method": "POST", "path": "/upload",
        "headers": [(b"content-length", b"10")],  # understated on purpose
    }
    asyncio.run(middleware(scope, receive, send))

    status = sent[0]["status"]
    assert status == 413, sent[0]
    assert b"exceeds" in sent[1]["body"]


def test_non_numeric_content_length_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "not-a-number"},
    )
    assert response.status_code == 400


def test_read_requests_are_not_size_limited(client: TestClient) -> None:
    # A long query string is a GET; the body cap must not interfere with it.
    response = client.get("/api/v1/tasks", params={"limit": 1})
    assert response.status_code == 200


def test_security_headers_are_not_duplicated(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    duplicates = [key for key in set(response.headers.keys()) if len(response.headers.get_list(key)) > 1]
    assert duplicates == []


def test_oversized_body_is_drained_before_the_413(client: TestClient) -> None:
    """The client must receive a real 413, not a broken pipe.

    Draining matters behind an intermediary: if the server answers and closes
    mid-upload, Vite's dev proxy reports its own 500 instead of our clear 413.
    """
    import asyncio

    from app.hardening import BodySizeLimitMiddleware

    received_all = {"value": False}

    async def inner(scope, receive, send):  # pragma: no cover - must not be reached
        raise AssertionError("handler ran for an oversized body")

    sent: list[dict] = []
    chunks = [b"x" * 500_000, b"x" * 500_000, b"x" * 200_000]

    async def receive():
        if chunks:
            more = len(chunks) > 1
            body = chunks.pop(0)
            if not more:
                received_all["value"] = True  # the announced body was fully consumed
            return {"type": "http.request", "body": body, "more_body": more}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(inner, max_bytes=1_000_000)
    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/projects",
        "headers": [(b"content-length", b"1200000")],
    }
    asyncio.run(middleware(scope, receive, send))

    assert sent[0]["status"] == 413
    assert received_all["value"] is True, "the body was not drained before replying"


def test_drain_is_bounded_for_a_client_that_under_delivers(client: TestClient) -> None:
    """A client that announces more than it sends must not hang the server."""
    import asyncio

    from app.hardening import BodySizeLimitMiddleware

    async def inner(scope, receive, send):  # pragma: no cover
        raise AssertionError("unreachable")

    sent: list[dict] = []
    calls = {"n": 0}

    async def receive():
        calls["n"] += 1
        if calls["n"] > 3:
            # Pretend the peer stops sending without closing.
            await asyncio.sleep(3600)
        return {"type": "http.request", "body": b"y" * 1_000, "more_body": True}

    async def send(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(inner, max_bytes=100)
    scope = {
        "type": "http", "method": "POST", "path": "/x",
        "headers": [(b"content-length", b"200"), (b"transfer-encoding", b"chunked")],
    }
    asyncio.run(asyncio.wait_for(middleware(scope, receive, send), timeout=2))
    assert sent[0]["status"] == 413

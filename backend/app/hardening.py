"""Request hardening for a local-first service.

Two bounded guarantees, both cheap and both testable:

* **Body size.** Mutating requests are capped before the handler sees them, so a
  multi-megabyte payload cannot be buffered into memory just to fail validation.
  The limit is generous for real documents and small enough to be safe.
* **Response headers.** The UI never needs to be framed, sniffed or to load
  third-party script, so those are refused with headers rather than by promise.

The middleware is ASGI-level, so it also covers requests FastAPI rejects early.
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 1_000_000  # 1 MB: comfortably above the largest legitimate form.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    # The UI is served by Vite in development and as static files in production;
    # nothing in the API needs to load or embed anything, so deny by default.
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    # Drain the announced body before replying. Answering and
                    # closing mid-upload makes an intermediary (Vite's dev proxy,
                    # for example) report its own 500 instead of our 413.
                    await self._drain(receive, int(declared))
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    {"detail": "Content-Length must be a number."}, status_code=400
                )
                await response(scope, receive, send)
                return

        # Stream the body through, counting as it arrives: a lying or absent
        # Content-Length must not get past the cap.
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._reject(scope, receive, send)

    async def _drain(self, receive: Receive, declared: int, hard_cap: int = 32_000_000) -> None:
        """Read and discard the announced body, bounded hard.

        The cap is only an announcement; the hard bound stops a client that
        claims a huge body and never sends it from holding the connection open.
        """
        remaining = min(declared, hard_cap)
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            remaining -= len(message.get("body", b""))
            # Stop on the declared length or on the final chunk, whichever comes
            # first: draining must never wait for a body the client stopped sending.
            if remaining <= 0 or not message.get("more_body"):
                return

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {
                "detail": f"Request body exceeds the {self.max_bytes} byte limit.",
                "limit_bytes": self.max_bytes,
            },
            status_code=413,
        )
        await response(scope, receive, send)


class _BodyTooLarge(Exception):
    """Internal signal: the streamed body crossed the limit mid-read."""


class SecurityHeadersMiddleware:
    """Adds hardening headers to every response that does not already set them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                headers = list(message.get("headers", []))
                for name, value in SECURITY_HEADERS:
                    if name not in present:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

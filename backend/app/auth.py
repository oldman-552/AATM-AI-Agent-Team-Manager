"""Local authentication for the AATM API.

Threat model: AATM is a single-user, loopback-first application. The realistic
local risks are (a) another process or a malicious web page driving the API,
and (b) CSRF from a browser that can reach loopback.

Design:

* When ``AATM_AUTH_MODE=off`` (default) the API behaves as before, but mutating
  requests are still refused if they carry a foreign ``Origin``. This keeps the
  default developer experience while blocking the classic browser CSRF vector.
* When ``AATM_AUTH_MODE=token`` every ``/api/v1`` request needs a bearer token.
  The token is never handed to the browser: the Vite dev proxy injects it
  server-side from the process environment, so the frontend bundle contains no
  secret.
* Tokens are compared in constant time, and never logged.
"""

import hmac
import os
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
AUTH_MODES = ("off", "token")
PUBLIC_PATHS = frozenset({"/", "/api/v1/health", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"})


@dataclass(frozen=True)
class AuthConfig:
    mode: str = "off"
    token: str | None = None
    allowed_origins: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.mode == "token"

    @classmethod
    def from_settings(cls, allowed_origins: list[str] | None = None) -> "AuthConfig":
        mode = (os.environ.get("AATM_AUTH_MODE") or "off").strip().lower()
        if mode not in AUTH_MODES:
            mode = "off"
        token = (os.environ.get("AATM_AUTH_TOKEN") or "").strip() or None
        if mode == "token" and not token:
            # Fail closed on configuration: refuse to run "authenticated" without a token.
            raise RuntimeError("AATM_AUTH_MODE=token requires AATM_AUTH_TOKEN to be set.")
        origins = tuple(allowed_origins or ())
        return cls(mode=mode, token=token, allowed_origins=origins)


def _bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


class LocalAuthMiddleware(BaseHTTPMiddleware):
    """Enforce optional bearer auth plus an origin check on mutations."""

    def __init__(self, app, config: AuthConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS and request.method in SAFE_METHODS:
            return await call_next(request)

        origin = request.headers.get("origin")
        if request.method not in SAFE_METHODS and origin and origin not in self.config.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-origin mutations are not allowed."},
            )

        if self.config.enabled:
            supplied = _bearer(request.headers.get("authorization"))
            expected = self.config.token or ""
            if not supplied or not hmac.compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required."},
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return await call_next(request)

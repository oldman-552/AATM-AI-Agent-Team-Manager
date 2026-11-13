"""Credential *references*, never credential values.

AATM never stores an API key in the database, accepts one over HTTP, logs one,
or returns one to the frontend. Configuration only holds references such as
``env:ANTHROPIC_API_KEY`` or ``keyring:aatm/anthropic``. Resolution happens in
process and only for an authorized execution attempt.
"""

import os
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from app.providers.contracts import InvalidCredentialRef

CredentialScheme = Literal["env", "keyring"]

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_KEYRING_LOCATOR = re.compile(r"^[A-Za-z0-9_.\-]{1,80}/[A-Za-z0-9_.\-@]{1,80}$")
_REF = re.compile(r"^(env|keyring):(.+)$")


@dataclass(frozen=True)
class CredentialRef:
    """A validated, secret-free locator for a credential."""

    scheme: CredentialScheme
    locator: str

    def __str__(self) -> str:
        return f"{self.scheme}:{self.locator}"

    def public(self) -> dict[str, str]:
        """Safe-to-serialize description; deliberately contains no secret."""
        return {"scheme": self.scheme, "locator": self.locator, "reference": str(self)}


def parse_credential_ref(value: str | None) -> CredentialRef | None:
    """Parse and validate a reference; reject raw keys and unknown schemes."""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    match = _REF.fullmatch(candidate)
    if match is None:
        raise InvalidCredentialRef(
            "Credential must be a reference in the form 'env:NAME' or 'keyring:service/account'; raw keys are not accepted."
        )
    scheme, locator = match.group(1), match.group(2)
    if scheme == "env":
        if not _ENV_NAME.fullmatch(locator):
            raise InvalidCredentialRef("env references require a valid environment variable name.")
        return CredentialRef("env", locator)
    if not _KEYRING_LOCATOR.fullmatch(locator):
        raise InvalidCredentialRef("keyring references require 'service/account'.")
    return CredentialRef("keyring", locator)


class CredentialStore(Protocol):
    """Resolution boundary; implementations must not log or persist values."""

    def is_available(self, ref: CredentialRef) -> bool: ...

    def resolve(self, ref: CredentialRef) -> str | None: ...


class EnvironmentCredentialStore:
    """Read-only environment-variable reference store."""

    def is_available(self, ref: CredentialRef) -> bool:
        return ref.scheme == "env" and bool(os.environ.get(ref.locator))

    def resolve(self, ref: CredentialRef) -> str | None:
        if ref.scheme != "env":
            return None
        return os.environ.get(ref.locator) or None


class KeyringCredentialStore:
    """Optional OS keyring support; unavailable backends fail closed."""

    def is_available(self, ref: CredentialRef) -> bool:
        return self.resolve(ref) is not None

    def resolve(self, ref: CredentialRef) -> str | None:
        if ref.scheme != "keyring":
            return None
        try:
            import keyring  # optional dependency, imported lazily
        except ImportError:
            return None
        service, account = ref.locator.split("/", 1)
        try:
            return keyring.get_password(service, account) or None
        except Exception:
            # A missing Secret Service / locked keyring is a normal local condition.
            return None


class CompositeCredentialStore:
    def __init__(self, stores: list[CredentialStore] | None = None) -> None:
        self.stores = stores or [EnvironmentCredentialStore(), KeyringCredentialStore()]

    def is_available(self, ref: CredentialRef) -> bool:
        return any(store.is_available(ref) for store in self.stores)

    def resolve(self, ref: CredentialRef) -> str | None:
        for store in self.stores:
            value = store.resolve(ref)
            if value:
                return value
        return None


def default_credential_store() -> CompositeCredentialStore:
    return CompositeCredentialStore()


def redact_secrets(message: str, store: CredentialStore, refs: list[CredentialRef]) -> str:
    """Remove resolved credential values from any text before it is logged/returned."""
    cleaned = message
    for ref in refs:
        value = store.resolve(ref)
        if value and len(value) >= 4:
            cleaned = cleaned.replace(value, "[REDACTED]")
    return cleaned

"""Offline provider configuration and evaluation context."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.budgets import BudgetGuard
from app.providers.contracts import RoutingPolicy
from app.providers.credentials import CredentialRef, CredentialStore, default_credential_store
from app.providers.pricing import PricingTable


@dataclass(frozen=True)
class ProviderConfigData:
    provider_id: str
    enabled: bool = False
    credential_ref: CredentialRef | None = None
    model: str | None = None
    base_url: str | None = None
    # Hard kill switch: the local HTTP API never permits live provider calls.
    live_requests_allowed: bool = False

    def public(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "enabled": self.enabled,
            "credential": self.credential_ref.public() if self.credential_ref else None,
            "model": self.model,
            "base_url": self.base_url,
            "live_requests_allowed": self.live_requests_allowed,
        }


@dataclass(frozen=True)
class ProviderSettingsData:
    routing_policy: RoutingPolicy = "arena_first"
    # A label to be replaced by a verified model id; no availability is claimed.
    default_model: str = "claude-sonnet-4-5"
    user_defined_order: tuple[str, ...] = ("arena_bridge", "anthropic")
    # Global kill switch. Tests may enable it while injecting a fake client.
    live_requests_allowed: bool = False
    arena_compliance_verified: bool = False

    def public(self) -> dict[str, object]:
        return {
            "routing_policy": self.routing_policy,
            "default_model": self.default_model,
            "user_defined_order": list(self.user_defined_order),
            "live_requests_allowed": self.live_requests_allowed,
            "arena_compliance_verified": self.arena_compliance_verified,
        }


@dataclass
class ProviderContext:
    """Everything an adapter may inspect. No network client is created here."""

    config: ProviderConfigData
    settings: ProviderSettingsData
    guard: BudgetGuard
    pricing: PricingTable = field(default_factory=PricingTable.from_env)
    store: CredentialStore = field(default_factory=default_credential_store)
    client: Any | None = None
    now: datetime | None = None

    @property
    def credential_available(self) -> bool:
        ref = self.config.credential_ref
        return bool(ref and self.store.is_available(ref))

    def resolved_model(self, requested: str | None = None) -> str:
        return requested or self.config.model or self.settings.default_model

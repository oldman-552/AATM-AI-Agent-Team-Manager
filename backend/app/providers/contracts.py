"""Pure data contracts for the provider boundary (no I/O, no secrets)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

ProviderId = Literal["arena_bridge", "anthropic"]
RoutingPolicy = Literal["arena_first", "claude_first", "manual", "task_based", "user_defined"]
TaskComplexity = Literal["low", "medium", "high"]
ProviderState = Literal[
    "offline_ready",
    "unconfigured",
    "disabled",
    "blocked",
    "budget_exhausted",
    "not_permitted",
]
BudgetScope = Literal["daily", "monthly", "agent", "project", "credential", "global"]

PROVIDER_IDS: tuple[ProviderId, ...] = ("arena_bridge", "anthropic")
ROUTING_POLICIES: tuple[RoutingPolicy, ...] = (
    "arena_first",
    "claude_first",
    "manual",
    "task_based",
    "user_defined",
)
BUDGET_SCOPES: tuple[BudgetScope, ...] = (
    "daily",
    "monthly",
    "agent",
    "project",
    "credential",
    "global",
)
TASK_COMPLEXITIES: tuple[TaskComplexity, ...] = ("low", "medium", "high")


class ProviderError(RuntimeError):
    """Base class for provider-boundary failures that are safe to report."""


class ProviderBlocked(ProviderError):
    """The provider is intentionally disabled for compliance reasons."""


class ProviderExecutionDisabled(ProviderError):
    """Live execution was not explicitly authorized by the caller."""


class InvalidCredentialRef(ProviderError):
    """A credential reference is malformed or unsupported."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ProviderHealth:
    """Offline health of a provider. ``live_calls_enabled`` is always False for the API."""

    provider_id: str
    state: ProviderState
    enabled: bool
    credential_available: bool
    reasons: tuple[str, ...] = ()
    live_calls_enabled: bool = False
    checked_at: str = field(default_factory=utc_now_iso)

    @property
    def eligible_for_routing(self) -> bool:
        return self.state in {"offline_ready", "budget_exhausted"}

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "state": self.state,
            "enabled": self.enabled,
            "credential_available": self.credential_available,
            "reasons": list(self.reasons),
            "live_calls_enabled": self.live_calls_enabled,
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class CostEstimate:
    """An estimate, never a confirmed provider billing record."""

    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    billing_status: str = "estimated"
    confirmed_cost_usd: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "billing_status": self.billing_status,
            "confirmed_cost_usd": self.confirmed_cost_usd,
        }


@dataclass(frozen=True)
class ProviderRequest:
    """A preflight/execution description. It never contains a secret value."""

    provider_id: str
    model: str
    messages: tuple[dict[str, str], ...]
    max_tokens: int = 1024
    system: str = ""
    agent_id: str | None = None
    project_id: str | None = None
    credential_ref: str | None = None
    idempotency_key: str = ""
    paid_consent: bool = False
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    live_execution_authorized: bool = False


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    model: str
    request_key: str
    text: str
    input_tokens: int
    output_tokens: int
    cost: CostEstimate

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "request_key": self.request_key,
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost.as_dict(),
        }


@dataclass(frozen=True)
class BudgetCheck:
    allowed: bool
    reason: str
    estimated_cost_usd: float
    applied_limits: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "applied_limits": [dict(item) for item in self.applied_limits],
        }


@dataclass(frozen=True)
class Authorization:
    allowed: bool
    reason: str
    estimate: CostEstimate
    budget: BudgetCheck


@dataclass(frozen=True)
class RoutingDecision:
    status: Literal["selected", "no_eligible_provider"]
    policy: RoutingPolicy
    provider_id: str | None
    model: str | None
    reasons: tuple[str, ...]
    cost: CostEstimate | None
    budget: BudgetCheck | None
    candidates: tuple[dict[str, object], ...] = ()
    execution_performed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "policy": self.policy,
            "provider_id": self.provider_id,
            "model": self.model,
            "reasons": list(self.reasons),
            "cost": self.cost.as_dict() if self.cost else None,
            "budget": self.budget.as_dict() if self.budget else None,
            "candidates": [dict(item) for item in self.candidates],
            "execution_performed": self.execution_performed,
        }

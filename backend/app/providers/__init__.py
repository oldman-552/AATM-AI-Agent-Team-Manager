"""Safe provider abstraction boundary for AATM.

This package defines configuration, credential references, health, budget
enforcement, routing and adapter contracts. Importing or using the health,
budget and routing surfaces never performs a network request. Live provider
execution is disabled for the local API and is only reachable through an
explicitly injected client in an authorized caller.
"""

from app.providers.contracts import (
    PROVIDER_IDS,
    ROUTING_POLICIES,
    Authorization,
    BudgetCheck,
    CostEstimate,
    ProviderBlocked,
    ProviderError,
    ProviderExecutionDisabled,
    ProviderHealth,
    ProviderRequest,
    ProviderResult,
    RoutingDecision,
)
from app.providers.credentials import (
    CredentialRef,
    CredentialStore,
    EnvironmentCredentialStore,
    InvalidCredentialRef,
    default_credential_store,
    parse_credential_ref,
    redact_secrets,
)
from app.providers.pricing import PricingTable, estimate_cost
from app.providers.budgets import BudgetGuard, BudgetLimit, InMemoryUsageRepository, UsageRepository
from app.providers.routing import RoutingEngine
from app.providers.registry import ProviderRegistry, default_registry

__all__ = [
    "PROVIDER_IDS",
    "ROUTING_POLICIES",
    "Authorization",
    "BudgetCheck",
    "BudgetGuard",
    "BudgetLimit",
    "CostEstimate",
    "CredentialRef",
    "CredentialStore",
    "EnvironmentCredentialStore",
    "InMemoryUsageRepository",
    "InvalidCredentialRef",
    "PricingTable",
    "ProviderBlocked",
    "ProviderError",
    "ProviderExecutionDisabled",
    "ProviderHealth",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResult",
    "RoutingDecision",
    "RoutingEngine",
    "UsageRepository",
    "default_credential_store",
    "default_registry",
    "estimate_cost",
    "parse_credential_ref",
    "redact_secrets",
]

"""Deterministic, offline routing policy evaluation.

A routing decision is a dry run: it selects which provider *would* be used and
records the reason for every rejected candidate. It never calls a provider,
never spends money, and never falls back to a paid provider without explicit
per-request consent plus a passing budget check.
"""

from dataclasses import dataclass
from typing import Callable

from app.providers.contracts import (
    ProviderRequest,
    RoutingDecision,
    RoutingPolicy,
    TaskComplexity,
)
from app.providers.context import ProviderContext, ProviderSettingsData
from app.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class RouteContext:
    policy: RoutingPolicy | None = None
    preferred_provider: str | None = None
    provider_order: tuple[str, ...] | None = None
    complexity: TaskComplexity = "medium"
    agent_id: str | None = None
    project_id: str | None = None
    model: str | None = None
    estimated_input_tokens: int = 1000
    estimated_output_tokens: int = 1024
    max_tokens: int = 1024
    paid_consent: bool = False


class RoutingEngine:
    def __init__(
        self,
        registry: ProviderRegistry,
        context_for: Callable[[str], ProviderContext],
        settings: Callable[[], ProviderSettingsData],
    ) -> None:
        self.registry = registry
        self.context_for = context_for
        self.settings = settings

    def _candidate_order(self, route: RouteContext, policy: RoutingPolicy) -> tuple[str, ...]:
        if policy == "manual":
            return (route.preferred_provider,) if route.preferred_provider else ()
        if policy == "user_defined":
            return tuple(route.provider_order or self.settings().user_defined_order)
        if policy == "arena_first":
            return ("arena_bridge", "anthropic")
        if policy == "claude_first":
            return ("anthropic", "arena_bridge")
        # task_based: prefer the free/blocked primary for simpler work, Claude for complex work.
        if route.complexity == "high":
            return ("anthropic", "arena_bridge")
        return ("arena_bridge", "anthropic")

    def resolve(self, route: RouteContext) -> RoutingDecision:
        settings = self.settings()
        policy = route.policy or settings.routing_policy
        order = self._candidate_order(route, policy)
        reasons: list[str] = []
        candidates: list[dict[str, object]] = []

        if not order:
            reasons.append("Manual routing requires an explicit preferred provider.")
        for provider_id in order:
            adapter = self.registry.get(provider_id)
            if adapter is None:
                reasons.append(f"Unknown provider '{provider_id}' was ignored.")
                candidates.append({"provider_id": provider_id, "allowed": False, "reason": "Unknown provider."})
                continue
            ctx = self.context_for(provider_id)
            health = adapter.health(ctx)
            request = ProviderRequest(
                provider_id=provider_id,
                model=ctx.resolved_model(route.model),
                messages=(),
                max_tokens=route.max_tokens,
                agent_id=route.agent_id,
                project_id=route.project_id,
                credential_ref=str(ctx.config.credential_ref) if ctx.config.credential_ref else None,
                estimated_input_tokens=route.estimated_input_tokens,
                estimated_output_tokens=route.estimated_output_tokens,
                paid_consent=route.paid_consent,
            )
            authorization = adapter.authorize(request, ctx)
            candidates.append(
                {
                    "provider_id": provider_id,
                    "health_state": health.state,
                    "allowed": authorization.allowed,
                    "reason": authorization.reason,
                    "estimated_cost_usd": round(authorization.estimate.estimated_cost_usd, 6),
                }
            )
            if authorization.allowed:
                reasons.append(f"{provider_id} passed offline configuration and budget checks.")
                reasons.append("Dry run only: no provider request was performed and no charge occurred.")
                return RoutingDecision(
                    status="selected",
                    policy=policy,
                    provider_id=provider_id,
                    model=request.model,
                    reasons=tuple(reasons),
                    cost=authorization.estimate,
                    budget=authorization.budget,
                    candidates=tuple(candidates),
                    execution_performed=False,
                )
            reasons.append(f"{provider_id}: {authorization.reason}")

        return RoutingDecision(
            status="no_eligible_provider",
            policy=policy,
            provider_id=None,
            model=None,
            reasons=tuple(reasons),
            cost=None,
            budget=None,
            candidates=tuple(candidates),
            execution_performed=False,
        )

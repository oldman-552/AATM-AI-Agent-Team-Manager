"""Provider adapters. Health/authorization are strictly offline.

Only ``AnthropicAdapter.execute`` can reach the official Anthropic SDK, and it
requires (1) an explicit per-request authorization flag, (2) the global live
request switch, (3) a resolvable credential *reference*, (4) explicit paid
consent, and (5) a passing budget check. The AATM HTTP API exposes no route
that calls ``execute``. Tests inject a fake SDK client; no network call is made.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.providers.budgets import UsageRecordData
from app.providers.context import ProviderContext
from app.providers.contracts import (
    Authorization,
    BudgetCheck,
    CostEstimate,
    ProviderBlocked,
    ProviderError,
    ProviderExecutionDisabled,
    ProviderHealth,
    ProviderRequest,
    ProviderResult,
    utc_now_iso,
)
from app.providers.credentials import redact_secrets

ARENA_BLOCK_REASONS: tuple[str, ...] = (
    "Arena Local Bridge v1.1.0 source automates an undocumented web UI and generates reCAPTCHA chat-submit tokens; this conflicts with the AATM no-bypass requirement.",
    "No officially supported, compliant Arena provider route has been verified; see PROVIDER_RESEARCH.md and BLOCKERS.txt.",
    "This adapter performs no requests, stores no Arena session, and cannot be enabled through the API.",
)


class ProviderAdapter(ABC):
    provider_id: str
    display_name: str
    is_paid: bool
    description: str
    compliance_note: str

    @abstractmethod
    def health(self, ctx: ProviderContext) -> ProviderHealth: ...

    @abstractmethod
    def authorize(self, request: ProviderRequest, ctx: ProviderContext) -> Authorization: ...

    def execute(self, request: ProviderRequest, ctx: ProviderContext) -> ProviderResult:
        raise ProviderExecutionDisabled(
            f"Live execution is not available for {self.provider_id} in this build."
        )

    def descriptor(self, ctx: ProviderContext) -> dict[str, object]:
        health = self.health(ctx)
        return {
            "id": self.provider_id,
            "name": self.display_name,
            "description": self.description,
            "is_paid": self.is_paid,
            "compliance_note": self.compliance_note,
            "config": ctx.config.public(),
            "health": health.as_dict(),
        }


class ArenaBridgeAdapter(ProviderAdapter):
    provider_id = "arena_bridge"
    display_name = "Arena Agent (Local Bridge)"
    is_paid = False
    description = "Primary provider target; statically inspected, intentionally disabled."
    compliance_note = "BLOCKED — no verified no-CAPTCHA-bypass route."

    def health(self, ctx: ProviderContext) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            state="blocked",
            enabled=False,
            credential_available=ctx.credential_available,
            reasons=ARENA_BLOCK_REASONS,
            live_calls_enabled=False,
            checked_at=utc_now_iso(),
        )

    def authorize(self, request: ProviderRequest, ctx: ProviderContext) -> Authorization:
        estimate = CostEstimate(request.model, 0, 0, 0.0)
        return Authorization(
            allowed=False,
            reason="Arena provider integration is blocked pending a compliant supported route.",
            estimate=estimate,
            budget=BudgetCheck(False, "Blocked provider; no usage is authorized.", 0.0),
        )

    def execute(self, request: ProviderRequest, ctx: ProviderContext) -> ProviderResult:
        raise ProviderBlocked("Arena execution is blocked; no CAPTCHA, session or web automation is used.")


class AnthropicAdapter(ProviderAdapter):
    provider_id = "anthropic"
    display_name = "Anthropic Claude API"
    is_paid = True
    description = "Official Anthropic SDK adapter; offline plumbing only until explicitly enabled."
    compliance_note = "Paid usage requires explicit consent, a positive budget, and a verified model."

    def health(self, ctx: ProviderContext) -> ProviderHealth:
        reasons: list[str] = []
        state = "offline_ready"
        if not ctx.settings.live_requests_allowed:
            reasons.append("Live provider calls are disabled for the local API; only configuration/health/routing plumbing is verified.")
        if not ctx.config.enabled:
            state = "disabled"
            reasons.append("Provider is disabled in configuration.")
        if not ctx.config.model and not ctx.settings.default_model:
            state = "unconfigured"
            reasons.append("No model is configured.")
        if ctx.config.credential_ref is None:
            state = "unconfigured"
            reasons.append("No credential reference is configured (env:NAME or keyring:service/account).")
        elif not ctx.credential_available:
            state = "unconfigured"
            reasons.append("The configured credential reference is not available in this process.")
        positive = [limit for limit in ctx.guard.applicable_limits(self.provider_id) if limit.limit_usd > 0]
        if not positive:
            if state == "offline_ready":
                state = "budget_exhausted"
            reasons.append("No positive budget limit is configured; paid requests are denied by default.")
        if state == "offline_ready":
            reasons.append("Offline readiness verified; no network request was made and no charge can occur from health checks.")
        return ProviderHealth(
            provider_id=self.provider_id,
            state=state,
            enabled=ctx.config.enabled,
            credential_available=ctx.credential_available,
            reasons=tuple(reasons),
            live_calls_enabled=False,
            checked_at=utc_now_iso(),
        )

    def authorize(self, request: ProviderRequest, ctx: ProviderContext) -> Authorization:
        model = ctx.resolved_model(request.model)
        # Worst-case output tokens make the preflight estimate conservative.
        output_tokens = max(request.estimated_output_tokens, request.max_tokens)
        estimate = ctx.pricing.estimate(model, request.estimated_input_tokens, output_tokens)

        if not ctx.config.enabled:
            return Authorization(
                False,
                "Provider is disabled; enable it and configure a verified model first.",
                estimate,
                BudgetCheck(False, "Provider disabled.", estimate.estimated_cost_usd),
            )
        if ctx.config.credential_ref is None or not ctx.credential_available:
            return Authorization(
                False,
                "A resolvable credential reference is required before any paid request.",
                estimate,
                BudgetCheck(False, "Credential unavailable.", estimate.estimated_cost_usd),
            )

        budget = ctx.guard.check(
            estimate,
            provider_id=self.provider_id,
            agent_id=request.agent_id,
            project_id=request.project_id,
            credential_ref=request.credential_ref or str(ctx.config.credential_ref),
            paid_consent=request.paid_consent,
            is_paid=True,
            now=ctx.now,
        )
        return Authorization(budget.allowed, budget.reason, estimate, budget)

    def execute(self, request: ProviderRequest, ctx: ProviderContext) -> ProviderResult:
        if not request.live_execution_authorized:
            raise ProviderExecutionDisabled(
                "Live execution requires an explicit per-request authorization flag; the HTTP API never sets it."
            )
        if not ctx.settings.live_requests_allowed:
            raise ProviderExecutionDisabled("The global live provider switch is off.")
        authorization = self.authorize(request, ctx)
        if not authorization.allowed:
            raise ProviderError(authorization.reason)

        ref = ctx.config.credential_ref
        assert ref is not None  # guaranteed by authorize()
        secret = ctx.store.resolve(ref)
        if not secret:
            raise ProviderError("Credential reference could not be resolved.")

        client: Any = ctx.client
        if client is None:
            try:
                from anthropic import Anthropic  # official SDK, imported only here
            except ImportError as exc:
                raise ProviderError("The official Anthropic SDK is not installed.") from exc
            client = Anthropic(api_key=secret)

        kwargs: dict[str, Any] = {
            "model": ctx.resolved_model(request.model),
            "max_tokens": request.max_tokens,
            "messages": [dict(message) for message in request.messages],
        }
        if request.system:
            kwargs["system"] = request.system
        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:
            message = redact_secrets(str(exc), ctx.store, [ref])
            raise ProviderError(f"Provider request failed: {message}") from exc

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", request.estimated_input_tokens) or 0)
        output_tokens = int(getattr(usage, "output_tokens", request.max_tokens) or 0)
        text_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            part = getattr(block, "text", None)
            if part:
                text_parts.append(str(part))
        text = redact_secrets("".join(text_parts), ctx.store, [ref])

        cost = ctx.pricing.estimate(ctx.resolved_model(request.model), input_tokens, output_tokens)
        record = UsageRecordData(
            request_key=request.idempotency_key or f"exec-{utc_now_iso()}",
            provider_id=self.provider_id,
            model=cost.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost.estimated_cost_usd,
            agent_id=request.agent_id,
            project_id=request.project_id,
            credential_ref=str(ref),
        )
        ctx.guard.commit(record)
        return ProviderResult(
            provider_id=self.provider_id,
            model=cost.model,
            request_key=record.request_key,
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )

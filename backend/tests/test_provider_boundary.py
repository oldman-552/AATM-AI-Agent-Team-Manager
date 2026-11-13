"""Unit tests for the offline provider boundary. No provider network calls."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.providers.adapters import AnthropicAdapter, ArenaBridgeAdapter, ProviderAdapter
from app.providers.budgets import (
    BudgetGuard,
    BudgetLimit,
    InMemoryUsageRepository,
    UsageRecordData,
)
from app.providers.context import ProviderConfigData, ProviderContext, ProviderSettingsData
from app.providers.contracts import (
    ProviderBlocked,
    ProviderError,
    ProviderExecutionDisabled,
    ProviderRequest,
)
from app.providers.credentials import (
    EnvironmentCredentialStore,
    InvalidCredentialRef,
    parse_credential_ref,
    redact_secrets,
)
from app.providers.pricing import ModelRate, PricingTable
from app.providers.registry import ProviderRegistry
from app.providers.routing import RouteContext, RoutingEngine

SECRET = "sk-test-secret-value-1234"


class FakeMessages:
    def __init__(self, *, fail_with: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_with = fail_with

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=120, output_tokens=30),
            content=[SimpleNamespace(text="Done: no live provider was contacted.")],
        )


class FakeClient:
    def __init__(self, *, fail_with: str | None = None) -> None:
        self.messages = FakeMessages(fail_with=fail_with)


def make_context(
    *,
    provider_id: str = "anthropic",
    enabled: bool = True,
    credential: str | None = "env:AATM_TEST_KEY",
    live: bool = True,
    limits: list[BudgetLimit] | None = None,
    repository: InMemoryUsageRepository | None = None,
    client=None,
    settings: ProviderSettingsData | None = None,
) -> tuple[ProviderContext, InMemoryUsageRepository]:
    repo = repository or InMemoryUsageRepository()
    ref = parse_credential_ref(credential)
    config = ProviderConfigData(
        provider_id=provider_id,
        enabled=enabled,
        credential_ref=ref,
        model="test-model",
    )
    guard = BudgetGuard(
        limits if limits is not None else [BudgetLimit("daily", "anthropic", 5.0)],
        repo,
    )
    ctx = ProviderContext(
        config=config,
        settings=settings or ProviderSettingsData(live_requests_allowed=live),
        guard=guard,
        pricing=PricingTable({"test-model": ModelRate(1.0, 2.0)}),
        store=EnvironmentCredentialStore(),
        client=client,
    )
    return ctx, repo


@pytest.fixture(autouse=True)
def credential_env(monkeypatch):
    monkeypatch.setenv("AATM_TEST_KEY", SECRET)


def test_credential_references_are_validated_and_never_expose_values() -> None:
    ref = parse_credential_ref("env:AATM_TEST_KEY")
    assert ref is not None and ref.scheme == "env"
    assert str(ref) == "env:AATM_TEST_KEY"
    assert "value" not in str(ref.public()).lower() or SECRET not in str(ref.public())

    for invalid in ("sk-ant-real-key", "file:///etc/passwd", "env:9BAD", "keyring:no-slash"):
        with pytest.raises(InvalidCredentialRef):
            parse_credential_ref(invalid)

    store = EnvironmentCredentialStore()
    assert store.is_available(ref) is True
    assert store.resolve(ref) == SECRET
    assert redact_secrets(f"failed with {SECRET}", store, [ref]) == "failed with [REDACTED]"


def test_pricing_is_configurable_and_estimated_not_confirmed(monkeypatch) -> None:
    monkeypatch.setenv(
        "AATM_MODEL_PRICING",
        '{"local-model": {"input_per_million_usd": 1.0, "output_per_million_usd": 3.0}}',
    )
    estimate = PricingTable.from_env().estimate("local-model", 1000, 1000)
    assert estimate.estimated_cost_usd == 0.004
    assert estimate.billing_status == "estimated"
    assert estimate.confirmed_cost_usd is None
    assert "not confirmed provider billing" in PricingTable.from_env().describe()["basis"]


def test_budget_guard_enforces_consent_limits_and_idempotency() -> None:
    repo = InMemoryUsageRepository()
    guard = BudgetGuard(
        [BudgetLimit("daily", "anthropic", 0.01), BudgetLimit("monthly", "anthropic", 1.0)],
        repo,
    )
    estimate = PricingTable({"m": ModelRate(1.0, 1.0)}).estimate("m", 1000, 1000)
    assert estimate.estimated_cost_usd == 0.002

    denied = guard.check(
        estimate,
        provider_id="anthropic",
        agent_id="a1",
        project_id="p1",
        credential_ref="env:AATM_TEST_KEY",
        paid_consent=False,
        is_paid=True,
    )
    assert denied.allowed is False and "consent" in denied.reason.lower()

    allowed = guard.check(
        estimate,
        provider_id="anthropic",
        agent_id="a1",
        project_id="p1",
        credential_ref="env:AATM_TEST_KEY",
        paid_consent=True,
        is_paid=True,
    )
    assert allowed.allowed is True
    assert len(allowed.applied_limits) == 2

    record = UsageRecordData(
        request_key="req-1",
        provider_id="anthropic",
        model="m",
        input_tokens=1000,
        output_tokens=1000,
        estimated_cost_usd=0.009,
        agent_id="a1",
        project_id="p1",
        credential_ref="env:AATM_TEST_KEY",
    )
    guard.commit(record)
    guard.commit(record)  # replay must not double count
    assert len(repo.records) == 1

    exhausted = guard.check(
        estimate,
        provider_id="anthropic",
        agent_id="a1",
        project_id="p1",
        credential_ref="env:AATM_TEST_KEY",
        paid_consent=True,
        is_paid=True,
    )
    assert exhausted.allowed is False and "exceeded" in exhausted.reason

    no_limits = BudgetGuard([], repo).check(
        estimate,
        provider_id="anthropic",
        agent_id=None,
        project_id=None,
        credential_ref=None,
        paid_consent=True,
        is_paid=True,
    )
    assert no_limits.allowed is False and "denied by default" in no_limits.reason

    free = guard.check(
        estimate,
        provider_id="arena_bridge",
        agent_id=None,
        project_id=None,
        credential_ref=None,
        paid_consent=False,
        is_paid=False,
    )
    assert free.allowed is True


def test_monthly_and_per_scope_limits_are_enforced() -> None:
    repo = InMemoryUsageRepository()
    old = datetime.now(timezone.utc) - timedelta(days=40)
    repo.add(
        UsageRecordData(
            request_key="old",
            provider_id="anthropic",
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.9,
            created_at=old,
        )
    )
    guard = BudgetGuard(
        [BudgetLimit("daily", "anthropic", 1.0), BudgetLimit("monthly", "anthropic", 1.0)],
        repo,
    )
    assert guard.check(
        PricingTable().estimate("m", 0, 0),
        provider_id="anthropic",
        agent_id=None,
        project_id=None,
        credential_ref=None,
        paid_consent=True,
        is_paid=True,
    ).allowed is True

    scoped = BudgetGuard([BudgetLimit("agent", "anthropic", 1.0)], repo)
    missing_scope = scoped.check(
        PricingTable().estimate("m", 0, 0),
        provider_id="anthropic",
        agent_id=None,
        project_id=None,
        credential_ref=None,
        paid_consent=True,
        is_paid=True,
    )
    assert missing_scope.allowed is False and "no agent scope" in missing_scope.reason


def test_arena_adapter_is_hard_blocked() -> None:
    ctx, _ = make_context(provider_id="arena_bridge", enabled=False, credential=None)
    adapter = ArenaBridgeAdapter()
    health = adapter.health(ctx)
    assert health.state == "blocked"
    assert health.live_calls_enabled is False
    assert any("CAPTCHA" in reason for reason in health.reasons)

    request = ProviderRequest(provider_id="arena_bridge", model="x", messages=())
    assert adapter.authorize(request, ctx).allowed is False
    with pytest.raises(ProviderBlocked):
        adapter.execute(request, ctx)


def test_claude_adapter_health_and_execution_require_explicit_authorization() -> None:
    fake = FakeClient()
    ctx, repo = make_context(client=fake)
    adapter = AnthropicAdapter()
    assert adapter.health(ctx).state == "offline_ready"
    assert adapter.health(ctx).live_calls_enabled is False

    request = ProviderRequest(
        provider_id="anthropic",
        model="test-model",
        messages=({"role": "user", "content": "Hello"},),
        max_tokens=64,
        estimated_input_tokens=100,
        estimated_output_tokens=64,
        paid_consent=True,
        idempotency_key="req-exec-1",
    )
    with pytest.raises(ProviderExecutionDisabled):
        adapter.execute(request, ctx)
    assert fake.messages.calls == []

    authorized = replace(request, live_execution_authorized=True)
    result = adapter.execute(authorized, ctx)
    assert result.text.startswith("Done:")
    assert result.input_tokens == 120 and result.output_tokens == 30
    assert len(repo.records) == 1
    assert fake.messages.calls[0]["model"] == "test-model"

    # Replaying the same idempotency key records usage once.
    adapter.execute(authorized, ctx)
    assert len(repo.records) == 1

    no_consent = replace(request, paid_consent=False, live_execution_authorized=True)
    with pytest.raises(ProviderError) as excinfo:
        adapter.execute(no_consent, ctx)
    assert "consent" in str(excinfo.value)

    offline = replace(ctx, settings=ProviderSettingsData(live_requests_allowed=False))
    with pytest.raises(ProviderExecutionDisabled):
        adapter.execute(authorized, offline)


def test_provider_errors_redact_credentials() -> None:
    failing = FakeClient(fail_with=f"401 invalid key {SECRET}")
    ctx, _ = make_context(client=failing)
    request = ProviderRequest(
        provider_id="anthropic",
        model="test-model",
        messages=(),
        max_tokens=8,
        paid_consent=True,
        idempotency_key="req-fail",
        live_execution_authorized=True,
    )
    with pytest.raises(ProviderError) as excinfo:
        AnthropicAdapter().execute(request, ctx)
    assert SECRET not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)


def build_engine(repo: InMemoryUsageRepository, *, enabled: bool = True):
    claude, _ = make_context(enabled=enabled, repository=repo)
    arena, _ = make_context(provider_id="arena_bridge", enabled=False, credential=None, repository=repo)
    contexts = {"anthropic": claude, "arena_bridge": arena}
    settings = ProviderSettingsData(live_requests_allowed=False)
    registry = ProviderRegistry()
    return RoutingEngine(registry, lambda provider_id: contexts[provider_id], lambda: settings)


def test_routing_never_selects_paid_provider_without_consent() -> None:
    repo = InMemoryUsageRepository()
    engine = build_engine(repo)
    decision = engine.resolve(RouteContext(policy="arena_first", paid_consent=False))
    assert decision.status == "no_eligible_provider"
    assert decision.execution_performed is False
    assert any("blocked" in reason.lower() for reason in decision.reasons)
    assert any("consent" in reason.lower() for reason in decision.reasons)

    consented = engine.resolve(RouteContext(policy="arena_first", paid_consent=True))
    assert consented.status == "selected"
    assert consented.provider_id == "anthropic"
    assert consented.budget is not None and consented.budget.allowed is True
    assert consented.execution_performed is False
    assert len(repo.records) == 0  # routing never records usage or spends money


def test_routing_policies_are_deterministic_and_reject_unknown_providers() -> None:
    repo = InMemoryUsageRepository()
    engine = build_engine(repo)
    manual = engine.resolve(
        RouteContext(policy="manual", preferred_provider="arena_bridge", paid_consent=True)
    )
    assert manual.status == "no_eligible_provider"
    assert len(manual.candidates) == 1

    user_defined = engine.resolve(
        RouteContext(policy="user_defined", provider_order=("anthropic", "arena_bridge"), paid_consent=True)
    )
    assert user_defined.provider_id == "anthropic"

    complex_task = engine.resolve(
        RouteContext(policy="task_based", complexity="high", paid_consent=True)
    )
    assert complex_task.candidates[0]["provider_id"] == "anthropic"

    claude_first = engine.resolve(RouteContext(policy="claude_first", paid_consent=True))
    assert claude_first.provider_id == "anthropic"

    disabled = build_engine(repo, enabled=False).resolve(RouteContext(paid_consent=True))
    assert disabled.status == "no_eligible_provider"


def test_offline_health_and_routing_open_no_sockets(monkeypatch) -> None:
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Offline provider surfaces must not open network sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    ctx, _ = make_context()
    assert isinstance(AnthropicAdapter(), ProviderAdapter)
    assert AnthropicAdapter().health(ctx).state == "offline_ready"
    engine = build_engine(InMemoryUsageRepository())
    assert engine.resolve(RouteContext(paid_consent=True)).status == "selected"

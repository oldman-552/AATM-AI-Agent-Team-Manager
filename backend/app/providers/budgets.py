"""Hard, server-side budget enforcement for paid providers.

Rules enforced here (and nowhere bypassable in the API):

* A paid provider request is denied without explicit per-request consent.
* A paid provider request is denied when no positive budget limit applies.
* Every applicable limit (daily, monthly, agent, project, credential, global)
  must have room for the estimated cost.
* Estimates are local configuration values, distinct from confirmed billing.
* Usage records are keyed by an idempotency key so a replay cannot double count.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.providers.contracts import (
    BudgetCheck,
    BudgetScope,
    CostEstimate,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class BudgetLimit:
    scope: BudgetScope
    provider_id: str
    limit_usd: float
    scope_key: str | None = None

    def __post_init__(self) -> None:
        if self.limit_usd < 0:
            raise ValueError("Budget limits cannot be negative.")

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "provider_id": self.provider_id,
            "scope_key": self.scope_key,
            "limit_usd": round(self.limit_usd, 6),
        }


@dataclass(frozen=True)
class UsageRecordData:
    """A persisted usage row. It contains references, never secret values."""

    request_key: str
    provider_id: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    agent_id: str | None = None
    project_id: str | None = None
    credential_ref: str | None = None
    billing_status: str = "estimated"
    confirmed_cost_usd: float | None = None
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "request_key": self.request_key,
            "provider_id": self.provider_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "confirmed_cost_usd": self.confirmed_cost_usd,
            "billing_status": self.billing_status,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "credential_ref": self.credential_ref,
            "created_at": _aware(self.created_at).isoformat().replace("+00:00", "Z"),
        }

    @property
    def effective_cost(self) -> float:
        if self.billing_status == "confirmed" and self.confirmed_cost_usd is not None:
            return self.confirmed_cost_usd
        return self.estimated_cost_usd


class UsageRepository(Protocol):
    def list_for_provider(self, provider_id: str) -> list[UsageRecordData]: ...

    def get(self, request_key: str) -> UsageRecordData | None: ...

    def add(self, record: UsageRecordData) -> UsageRecordData: ...


class InMemoryUsageRepository:
    """Test/standalone implementation; production uses the SQLAlchemy store."""

    def __init__(self) -> None:
        self.records: list[UsageRecordData] = []

    def list_for_provider(self, provider_id: str) -> list[UsageRecordData]:
        return [record for record in self.records if record.provider_id == provider_id]

    def get(self, request_key: str) -> UsageRecordData | None:
        return next((r for r in self.records if r.request_key == request_key), None)

    def add(self, record: UsageRecordData) -> UsageRecordData:
        existing = self.get(record.request_key)
        if existing is not None:
            return existing
        self.records.append(record)
        return record


class BudgetGuard:
    """Evaluate and record paid usage without performing any provider request."""

    def __init__(self, limits: list[BudgetLimit], repository: UsageRepository) -> None:
        self.limits = list(limits)
        self.repository = repository

    def applicable_limits(self, provider_id: str) -> list[BudgetLimit]:
        return [limit for limit in self.limits if limit.provider_id in {provider_id, "*"}]

    def check(
        self,
        estimate: CostEstimate,
        *,
        provider_id: str,
        agent_id: str | None,
        project_id: str | None,
        credential_ref: str | None,
        paid_consent: bool,
        is_paid: bool,
        now: datetime | None = None,
    ) -> BudgetCheck:
        if not is_paid:
            return BudgetCheck(True, "No paid usage applies to this provider.", estimate.estimated_cost_usd)

        if not paid_consent:
            return BudgetCheck(
                False,
                "Explicit paid consent is required for every paid provider request.",
                estimate.estimated_cost_usd,
            )

        limits = self.applicable_limits(provider_id)
        positive_limits = [limit for limit in limits if limit.limit_usd > 0]
        if not positive_limits:
            return BudgetCheck(
                False,
                "No positive budget limit is configured; paid usage is denied by default.",
                estimate.estimated_cost_usd,
            )

        current = _aware(now or utc_now())
        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        records = self.repository.list_for_provider(provider_id)
        applied: list[dict[str, object]] = []

        for limit in positive_limits:
            filtered = records
            if limit.scope == "daily":
                filtered = [r for r in filtered if _aware(r.created_at) >= day_start]
            elif limit.scope == "monthly":
                filtered = [r for r in filtered if _aware(r.created_at) >= month_start]
            elif limit.scope == "agent":
                target = limit.scope_key or agent_id
                if target is None:
                    return BudgetCheck(
                        False,
                        "A per-agent budget is configured but no agent scope was supplied.",
                        estimate.estimated_cost_usd,
                    )
                filtered = [r for r in filtered if r.agent_id == target]
            elif limit.scope == "project":
                target = limit.scope_key or project_id
                if target is None:
                    return BudgetCheck(
                        False,
                        "A per-project budget is configured but no project scope was supplied.",
                        estimate.estimated_cost_usd,
                    )
                filtered = [r for r in filtered if r.project_id == target]
            elif limit.scope == "credential":
                target = limit.scope_key or credential_ref
                if target is None:
                    return BudgetCheck(
                        False,
                        "A per-key budget is configured but no credential reference was supplied.",
                        estimate.estimated_cost_usd,
                    )
                filtered = [r for r in filtered if r.credential_ref == target]

            used = round(sum(record.effective_cost for record in filtered), 6)
            remaining = round(limit.limit_usd - used, 6)
            applied.append(
                {
                    **limit.as_dict(),
                    "used_usd": used,
                    "remaining_usd": remaining,
                }
            )
            if used + estimate.estimated_cost_usd > limit.limit_usd + 1e-9:
                return BudgetCheck(
                    False,
                    f"{limit.scope} budget limit would be exceeded (used {used:.6f} + "
                    f"estimate {estimate.estimated_cost_usd:.6f} > {limit.limit_usd:.6f} USD).",
                    estimate.estimated_cost_usd,
                    tuple(applied),
                )

        return BudgetCheck(
            True,
            "All configured paid-usage limits allow this estimate.",
            estimate.estimated_cost_usd,
            tuple(applied),
        )

    def commit(self, record: UsageRecordData) -> UsageRecordData:
        """Idempotently persist an authorized usage record."""
        return self.repository.add(record)

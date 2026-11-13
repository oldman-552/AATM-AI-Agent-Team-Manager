"""SQLAlchemy-backed provider settings, budgets, usage and evaluation wiring."""

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, ProviderBudgetLimit, ProviderConfig, UsageRecord
from app.providers.budgets import (
    BudgetGuard,
    BudgetLimit,
    InMemoryUsageRepository,
    UsageRecordData,
    UsageRepository,
)
from app.providers.context import ProviderConfigData, ProviderContext, ProviderSettingsData
from app.providers.contracts import BUDGET_SCOPES, PROVIDER_IDS, ROUTING_POLICIES
from app.providers.credentials import default_credential_store, parse_credential_ref
from app.providers.pricing import PricingTable
from app.providers.registry import default_registry
from app.providers.routing import RoutingEngine

SETTINGS_KEY = "providers.settings"
REGISTRY = default_registry()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seed_provider_defaults(db: Session) -> None:
    """Create disabled provider rows and default settings exactly once."""
    changed = False
    for provider_id in PROVIDER_IDS:
        if db.get(ProviderConfig, provider_id) is None:
            db.add(ProviderConfig(id=provider_id, enabled=False))
            changed = True
    if db.get(AppSetting, SETTINGS_KEY) is None:
        db.add(AppSetting(key=SETTINGS_KEY, value=ProviderSettingsData().public()))
        changed = True
    if changed:
        db.commit()


def load_settings(db: Session) -> ProviderSettingsData:
    row = db.get(AppSetting, SETTINGS_KEY)
    raw = row.value if row and isinstance(row.value, dict) else {}
    policy = raw.get("routing_policy")
    order = raw.get("user_defined_order")
    return ProviderSettingsData(
        routing_policy=policy if policy in ROUTING_POLICIES else "arena_first",
        default_model=str(raw.get("default_model") or "claude-sonnet-4-5"),
        user_defined_order=tuple(
            item for item in (order if isinstance(order, list) else []) if item in PROVIDER_IDS
        ) or ("arena_bridge", "anthropic"),
        live_requests_allowed=False,  # hard-coded: the HTTP API never performs live provider calls
        arena_compliance_verified=False,
    )


def save_settings(db: Session, settings: ProviderSettingsData) -> None:
    row = db.get(AppSetting, SETTINGS_KEY)
    payload = settings.public()
    if row is None:
        db.add(AppSetting(key=SETTINGS_KEY, value=payload))
    else:
        row.value = payload
        row.updated_at = utc_now()


def get_config_row(db: Session, provider_id: str) -> ProviderConfig:
    row = db.get(ProviderConfig, provider_id)
    if row is None:
        row = ProviderConfig(id=provider_id, enabled=False)
        db.add(row)
        db.flush()
    return row


def to_config_data(row: ProviderConfig) -> ProviderConfigData:
    try:
        ref = parse_credential_ref(row.credential_ref)
    except Exception:
        # A legacy/invalid stored reference is treated as absent, never surfaced as a secret.
        ref = None
    return ProviderConfigData(
        provider_id=row.id,
        enabled=bool(row.enabled),
        credential_ref=ref,
        model=row.model,
        base_url=row.base_url,
        live_requests_allowed=False,
    )


def load_limits(db: Session) -> list[BudgetLimit]:
    rows = db.scalars(select(ProviderBudgetLimit).order_by(ProviderBudgetLimit.scope.asc())).all()
    return [
        BudgetLimit(
            scope=row.scope,  # type: ignore[arg-type]
            provider_id=row.provider_id,
            limit_usd=float(row.limit_usd),
            scope_key=row.scope_key or None,
        )
        for row in rows
        if row.scope in BUDGET_SCOPES
    ]


def upsert_limit(db: Session, limit: BudgetLimit) -> ProviderBudgetLimit:
    scope_key = limit.scope_key or ""
    row = db.scalar(
        select(ProviderBudgetLimit).where(
            ProviderBudgetLimit.scope == limit.scope,
            ProviderBudgetLimit.provider_id == limit.provider_id,
            ProviderBudgetLimit.scope_key == scope_key,
        )
    )
    if row is None:
        row = ProviderBudgetLimit(
            scope=limit.scope,
            provider_id=limit.provider_id,
            scope_key=scope_key,
            limit_usd=limit.limit_usd,
        )
        db.add(row)
    else:
        row.limit_usd = limit.limit_usd
        row.updated_at = utc_now()
    db.flush()
    return row


def _to_usage_data(row: UsageRecord) -> UsageRecordData:
    return UsageRecordData(
        request_key=row.request_key,
        provider_id=row.provider_id,
        model=row.model,
        input_tokens=int(row.input_tokens),
        output_tokens=int(row.output_tokens),
        estimated_cost_usd=float(row.estimated_cost_usd),
        agent_id=row.agent_id,
        project_id=row.project_id,
        credential_ref=row.credential_ref,
        billing_status=row.billing_status,
        confirmed_cost_usd=row.confirmed_cost_usd,
        created_at=row.created_at,
    )


class SqlUsageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_provider(self, provider_id: str) -> list[UsageRecordData]:
        rows = self.db.scalars(
            select(UsageRecord).where(UsageRecord.provider_id == provider_id)
        ).all()
        return [_to_usage_data(row) for row in rows]

    def get(self, request_key: str) -> UsageRecordData | None:
        row = self.db.scalar(select(UsageRecord).where(UsageRecord.request_key == request_key))
        return _to_usage_data(row) if row else None

    def add(self, record: UsageRecordData) -> UsageRecordData:
        existing = self.get(record.request_key)
        if existing is not None:
            return existing
        row = UsageRecord(
            request_key=record.request_key,
            provider_id=record.provider_id,
            model=record.model,
            agent_id=record.agent_id,
            project_id=record.project_id,
            credential_ref=record.credential_ref,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            estimated_cost_usd=record.estimated_cost_usd,
            confirmed_cost_usd=record.confirmed_cost_usd,
            billing_status=record.billing_status,
            created_at=record.created_at,
        )
        self.db.add(row)
        self.db.flush()
        return _to_usage_data(row)


def usage_repository(db: Session | None) -> UsageRepository:
    return SqlUsageRepository(db) if db is not None else InMemoryUsageRepository()


def budget_guard(db: Session) -> BudgetGuard:
    return BudgetGuard(load_limits(db), SqlUsageRepository(db))


def context_for(db: Session) -> Callable[[str], ProviderContext]:
    settings = load_settings(db)
    guard = budget_guard(db)
    store = default_credential_store()

    def build(provider_id: str) -> ProviderContext:
        config = to_config_data(get_config_row(db, provider_id))
        return ProviderContext(
            config=config,
            settings=settings,
            guard=guard,
            pricing=PricingTable.from_env(),
            store=store,
            client=None,
        )

    return build


def routing_engine(db: Session) -> RoutingEngine:
    return RoutingEngine(REGISTRY, context_for(db), lambda: load_settings(db))


def usage_summary(db: Session, limit: int = 50) -> dict[str, object]:
    """Aggregate usage from one query; costs stay explicitly estimated."""
    rows = list(
        db.scalars(select(UsageRecord).order_by(UsageRecord.created_at.desc())).all()
    )
    by_provider: dict[str, dict[str, object]] = {}
    for row in rows:
        bucket = by_provider.setdefault(
            row.provider_id,
            {"requests": 0, "estimated_cost_usd": 0.0, "confirmed_cost_usd": 0.0},
        )
        bucket["requests"] = int(bucket["requests"]) + 1
        bucket["estimated_cost_usd"] = round(
            float(bucket["estimated_cost_usd"]) + float(row.estimated_cost_usd), 6
        )
        if row.billing_status == "confirmed" and row.confirmed_cost_usd is not None:
            bucket["confirmed_cost_usd"] = round(
                float(bucket["confirmed_cost_usd"]) + float(row.confirmed_cost_usd), 6
            )
    return {
        "total_records": len(rows),
        "by_provider": by_provider,
        "records": [_to_usage_data(row).as_dict() for row in rows[: max(1, limit)]],
        "billing_note": "Costs are local estimates unless billing_status is 'confirmed'; no provider billing API is called.",
    }

"""Provider configuration, offline health, budgets, usage and routing API.

None of these endpoints performs a request to an external AI provider, reads a
credential value into a response, or accepts a raw secret. Live execution is
intentionally not exposed over HTTP in this build.
"""

from dataclasses import replace
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.audit import add_event
from app.models import Agent, Project
from app.provider_store import (
    REGISTRY,
    SETTINGS_KEY,
    context_for,
    get_config_row,
    load_limits,
    load_settings,
    routing_engine,
    save_settings,
    to_config_data,
    upsert_limit,
    usage_summary,
)
from app.providers.budgets import BudgetLimit
from app.providers.contracts import PROVIDER_IDS, ROUTING_POLICIES
from app.providers.pricing import PricingTable
from app.providers.routing import RouteContext
from app.schemas import BudgetLimitUpsert, ProviderConfigUpdate, ProviderSettingsUpdate, RouteRequest

provider_router = APIRouter(prefix="/api/v1/providers")
ops_router = APIRouter(prefix="/api/v1")


def get_session(request: Request):
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _require_provider(provider_id: str) -> None:
    if provider_id not in PROVIDER_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'.")


def _validate_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="base_url must be an http(s) URL.")
    allowed = {"api.anthropic.com", "localhost", "127.0.0.1", "::1"}
    if parsed.hostname not in allowed:
        raise HTTPException(
            status_code=422,
            detail="Only the official Anthropic host or a loopback proxy may be configured.",
        )
    return candidate


@provider_router.get("")
def list_providers(db=Depends(get_session)) -> dict[str, object]:
    """Offline catalog: configuration, health, budgets and estimate basis."""
    return {
        "providers": REGISTRY.describe_all(context_for(db)),
        "settings": load_settings(db).public(),
        "budget_limits": [limit.as_dict() for limit in load_limits(db)],
        "pricing": PricingTable.from_env().describe(),
        "live_requests_allowed": False,
        "note": "Health checks, budgets and routing are offline. No API exposes live provider execution.",
    }


@provider_router.get("/settings")
def get_provider_settings(db=Depends(get_session)) -> dict[str, object]:
    return load_settings(db).public()


@provider_router.patch("/settings")
def update_provider_settings(payload: ProviderSettingsUpdate, db=Depends(get_session)) -> dict[str, object]:
    current = load_settings(db)
    if payload.user_defined_order is not None:
        unknown = [item for item in payload.user_defined_order if item not in PROVIDER_IDS]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown provider(s) in order: {', '.join(unknown)}.")
    if payload.default_model is not None and not payload.default_model.strip():
        raise HTTPException(status_code=422, detail="default_model cannot be blank.")
    updated = replace(
        current,
        routing_policy=payload.routing_policy or current.routing_policy,
        default_model=payload.default_model.strip() if payload.default_model else current.default_model,
        user_defined_order=tuple(payload.user_defined_order) if payload.user_defined_order is not None else current.user_defined_order,
    )
    if updated.routing_policy not in ROUTING_POLICIES:
        raise HTTPException(status_code=422, detail="Unsupported routing policy.")
    save_settings(db, updated)
    add_event(db, "system", SETTINGS_KEY, "providers.settings_updated", f"Routing policy set to {updated.routing_policy}.")
    db.commit()
    return updated.public()


@provider_router.post("/route")
def evaluate_routing(payload: RouteRequest, db=Depends(get_session)) -> dict[str, object]:
    """Dry-run routing decision; no provider request and no charge."""
    if payload.preferred_provider and payload.preferred_provider not in PROVIDER_IDS:
        raise HTTPException(status_code=422, detail="Unknown preferred provider.")
    if payload.provider_order:
        unknown = [item for item in payload.provider_order if item not in PROVIDER_IDS]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown provider(s) in order: {', '.join(unknown)}.")
    if payload.agent_id and db.get(Agent, payload.agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    if payload.project_id and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    decision = routing_engine(db).resolve(
        RouteContext(
            policy=payload.policy,
            preferred_provider=payload.preferred_provider,
            provider_order=tuple(payload.provider_order) if payload.provider_order else None,
            complexity=payload.complexity,
            agent_id=payload.agent_id,
            project_id=payload.project_id,
            model=payload.model,
            estimated_input_tokens=payload.estimated_input_tokens,
            estimated_output_tokens=payload.estimated_output_tokens,
            max_tokens=payload.max_tokens,
            paid_consent=payload.paid_consent,
        )
    )
    return decision.as_dict()


@provider_router.get("/{provider_id}")
def get_provider(provider_id: str, db=Depends(get_session)) -> dict[str, object]:
    _require_provider(provider_id)
    adapter = REGISTRY.get(provider_id)
    assert adapter is not None
    return adapter.descriptor(context_for(db)(provider_id))


@provider_router.get("/{provider_id}/health")
def get_provider_health(provider_id: str, db=Depends(get_session)) -> dict[str, object]:
    """Offline health only. Never contacts the provider."""
    _require_provider(provider_id)
    adapter = REGISTRY.get(provider_id)
    assert adapter is not None
    return adapter.health(context_for(db)(provider_id)).as_dict()


@provider_router.patch("/{provider_id}/config")
def update_provider_config(
    provider_id: str,
    payload: ProviderConfigUpdate,
    db=Depends(get_session),
) -> dict[str, object]:
    """Update secret-free configuration; Arena remains hard-blocked."""
    _require_provider(provider_id)
    if payload.clear_credential and payload.credential_ref:
        raise HTTPException(status_code=422, detail="Use either credential_ref or clear_credential, not both.")

    if provider_id == "arena_bridge" and (
        payload.enabled is True or payload.model or payload.base_url or payload.credential_ref
    ):
        raise HTTPException(
            status_code=409,
            detail="Arena provider configuration is blocked pending a verified compliant route; see BLOCKERS.txt.",
        )

    base_url = _validate_base_url(payload.base_url)
    row = get_config_row(db, provider_id)
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.credential_ref is not None:
        row.credential_ref = payload.credential_ref
    if payload.clear_credential:
        row.credential_ref = None
    if payload.model is not None:
        row.model = payload.model.strip() or None
    if payload.base_url is not None:
        row.base_url = base_url
    row.enabled = False if provider_id == "arena_bridge" else bool(row.enabled)

    add_event(
        db,
        "provider",
        provider_id,
        "provider.config_updated",
        f"Provider {provider_id} configuration updated (credential references only; no secret values stored).",
    )
    db.commit()
    db.refresh(row)
    adapter = REGISTRY.get(provider_id)
    assert adapter is not None
    return {
        "config": to_config_data(row).public(),
        "health": adapter.health(context_for(db)(provider_id)).as_dict(),
    }


@ops_router.get("/budgets")
def get_budgets(db=Depends(get_session)) -> dict[str, object]:
    return {
        "limits": [limit.as_dict() for limit in load_limits(db)],
        "usage": usage_summary(db, limit=10),
        "note": "Paid usage is denied unless a positive applicable limit exists and consent is given per request.",
    }


@ops_router.put("/budgets", status_code=status.HTTP_200_OK)
def upsert_budget(payload: BudgetLimitUpsert, db=Depends(get_session)) -> dict[str, object]:
    if payload.provider_id not in PROVIDER_IDS and payload.provider_id != "*":
        raise HTTPException(status_code=422, detail="Unknown provider for budget limit.")
    limit = BudgetLimit(
        scope=payload.scope,
        provider_id=payload.provider_id,
        limit_usd=float(payload.limit_usd),
        scope_key=payload.scope_key,
    )
    upsert_limit(db, limit)
    add_event(
        db,
        "budget",
        None,
        "budget.limit_updated",
        f"Budget limit updated: {limit.scope} / {limit.provider_id} = {limit.limit_usd:.2f} USD.",
    )
    db.commit()
    return {"limit": limit.as_dict(), "limits": [item.as_dict() for item in load_limits(db)]}


@ops_router.get("/usage")
def get_usage(db=Depends(get_session)) -> dict[str, object]:
    return usage_summary(db)

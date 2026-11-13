"""Validated API input and output schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.contracts import BudgetScope, RoutingPolicy, TaskComplexity
from app.providers.credentials import InvalidCredentialRef, parse_credential_ref

Priority = Literal["low", "normal", "high", "urgent"]
TaskState = Literal[
    "pending",
    "assigned",
    "running",
    "waiting",
    "completed",
    "failed",
    "reviewing",
    "rework_required",
    "approved",
    "cancelled",
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank")
        return value


class ProjectRead(ORMModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10_000)
    system_instructions: str = Field(default="", max_length=20_000)
    provider: str = Field(default="unconfigured", min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=120)
    permissions: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("name", "role")
    @classmethod
    def required_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class AgentRead(ORMModel):
    id: str
    name: str
    role: str
    description: str
    system_instructions: str
    provider: str
    model: str | None
    status: str
    permissions: list[str] = Field(default_factory=list)
    is_manager: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    priority: Priority = "normal"
    assigned_agent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be blank")
        return value


class TaskRead(ORMModel):
    id: str
    project_id: str | None
    title: str
    description: str
    priority: str
    state: str
    assigned_agent_id: str | None
    dependencies: list[str]
    acceptance_criteria: list[str]
    retry_count: int
    output: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskAssignment(BaseModel):
    assigned_agent_id: str | None


class AuditEventRead(ORMModel):
    id: str
    entity_type: str
    entity_id: str | None
    event_type: str
    summary: str
    created_at: datetime


class ProviderConfigUpdate(BaseModel):
    """Safe provider configuration. Raw credential values are explicitly rejected."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    credential_ref: str | None = Field(default=None, max_length=200)
    clear_credential: bool = False
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)

    @field_validator("credential_ref")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ref = parse_credential_ref(value)
        except InvalidCredentialRef as exc:
            raise ValueError(str(exc)) from exc
        return str(ref) if ref else None


class ProviderSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routing_policy: RoutingPolicy | None = None
    default_model: str | None = Field(default=None, max_length=120)
    user_defined_order: list[str] | None = Field(default=None, max_length=10)


class BudgetLimitUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: BudgetScope
    provider_id: str = Field(min_length=1, max_length=64)
    scope_key: str | None = Field(default=None, max_length=200)
    limit_usd: float = Field(ge=0.0, le=1_000_000.0)


class RouteRequest(BaseModel):
    """Offline routing dry run. It never triggers a provider request."""

    model_config = ConfigDict(extra="forbid")

    policy: RoutingPolicy | None = None
    preferred_provider: str | None = Field(default=None, max_length=64)
    provider_order: list[str] | None = Field(default=None, max_length=10)
    complexity: TaskComplexity = "medium"
    agent_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
    model: str | None = Field(default=None, max_length=120)
    estimated_input_tokens: int = Field(default=1000, ge=0, le=1_000_000)
    estimated_output_tokens: int = Field(default=1024, ge=0, le=1_000_000)
    max_tokens: int = Field(default=1024, ge=1, le=200_000)
    paid_consent: bool = False


class TaskStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: TaskState
    idempotency_key: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=2000)
    output: str | None = Field(default=None, max_length=20_000)
    error: str | None = Field(default=None, max_length=20_000)

    @field_validator("idempotency_key")
    @classmethod
    def key_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value


class ReviewCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check: str = Field(min_length=1, max_length=200)
    result: str = Field(default="pass", max_length=200)


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_agent_id: str = Field(min_length=1, max_length=36)
    verdict: Literal["approved", "rework_required"]
    summary: str = Field(default="", max_length=500)
    checks: list[ReviewCheck] = Field(default_factory=list, max_length=50)
    idempotency_key: str = Field(min_length=1, max_length=160)

    @field_validator("idempotency_key")
    @classmethod
    def review_key_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    reviewer_agent_id: str | None
    verdict: str
    summary: str
    checks: list[dict[str, object]]
    created_at: datetime


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["paid_provider_request", "protected_branch_merge", "deployment", "data_deletion", "pull_request"]
    entity_type: str = Field(default="task", max_length=40)
    entity_id: str | None = Field(default=None, max_length=36)
    summary: str = Field(min_length=1, max_length=500)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    entity_type: str
    entity_id: str | None
    summary: str
    status: str
    requested_by: str
    decided_by: str | None
    decision_note: str
    requested_at: datetime
    decided_at: datetime | None

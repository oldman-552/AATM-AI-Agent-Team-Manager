"""Persistent domain records for the initial AATM foundation."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="unconfigured")
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    tasks: Mapped[list["Task"]] = relationship(back_populates="assigned_agent")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    project: Mapped[Project | None] = relationship(back_populates="tasks")
    assigned_agent: Mapped[Agent | None] = relationship(back_populates="tasks")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class ProviderConfig(Base):
    """Provider configuration. Holds credential *references* only, never values."""

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ProviderBudgetLimit(Base):
    """Hard server-side budget limits. Zero/negative rows deny paid usage."""

    __tablename__ = "provider_budget_limits"
    __table_args__ = (
        UniqueConstraint("scope", "provider_id", "scope_key", name="uq_provider_budget_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    limit_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class UsageRecord(Base):
    """Estimated (or later imported confirmed) provider usage. No secret values."""

    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confirmed_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    billing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="estimated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class AppSetting(Base):
    """Small JSON settings bag for provider routing preferences."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class TaskTransition(Base):
    """Append-only task state history with replay-safe idempotency keys."""

    __tablename__ = "task_transitions"
    __table_args__ = (
        UniqueConstraint("task_id", "idempotency_key", name="uq_task_transition_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class BrowserProfile(Base):
    """A registry entry and an isolated on-disk directory for a browser profile.

    Stores metadata only. Cookie jars, saved logins and session storage are never
    read, parsed or persisted by AATM; `session_state` is always
    ``not_inspected`` in this build.
    """

    __tablename__ = "browser_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    isolation: Mapped[str] = mapped_column(String(32), nullable=False, default="per_profile")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created", index=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_inspected")
    profile_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class NotificationRead(Base):
    """Persisted read state for derived notifications.

    Notifications themselves are computed from live rows, so only the ids a user
    has already seen need storing.
    """

    __tablename__ = "notification_reads"

    notification_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class GithubPullRequest(Base):
    """A recorded, approval-gated pull-request plan.

    `executed` stays false in this build: the record documents intent and the
    gate, and no token, network call or push is involved.
    """

    __tablename__ = "github_pull_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(39), nullable=False)
    repo: Mapped[str] = mapped_column(String(100), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(121), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(121), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting_approval", index=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approval_requests.id"), nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class TaskCheckpoint(Base):
    """A durable resume point for interrupted work.

    Checkpoints are append-only observations written *before* risky work and at
    meaningful milestones. They never store credentials: `state` is a small,
    structured snapshot (counters, ids, paths) and `note` is free text that the
    caller is responsible for keeping secret-free.
    """

    __tablename__ = "task_checkpoints"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_task_checkpoint_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class ReviewRecord(Base):
    """An independent review verdict with explicit evidence.

    Reviewer separation is enforced in the service layer: the reviewer must be
    a different agent from the assignee, and `approved` cannot be recorded
    without at least one concrete check.
    """

    __tablename__ = "review_records"
    __table_args__ = (
        UniqueConstraint("task_id", "idempotency_key", name="uq_review_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    reviewer_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class ApprovalRequest(Base):
    """A gated operation awaiting explicit human approval.

    Approval-gated actions (paid provider traffic, protected merges, deploys)
    record intent here; executing them is a separate, authorized step that does
    not exist yet.
    """

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False, default="local-user")
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectWorkspace(Base):
    """Isolated Git workspace bound to a project. One workspace per project."""

    __tablename__ = "project_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    root_path: Mapped[str] = mapped_column(String(500), nullable=False)
    workspace_path: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class MemoryEntry(Base):
    """Project-isolated memory. Non-global rows are only visible inside their project."""

    __tablename__ = "memory_entries"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_memory_project_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="project", index=True)
    key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class MemoryVersion(Base):
    """Immutable version history for a memory entry (never rewritten in place)."""

    __tablename__ = "memory_versions"
    __table_args__ = (
        UniqueConstraint("entry_id", "version", name="uq_memory_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entry_id: Mapped[str] = mapped_column(ForeignKey("memory_entries.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

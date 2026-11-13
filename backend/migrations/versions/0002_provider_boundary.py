"""Provider boundary, budgets, usage, settings and task transition history.

Revision ID: 0002_provider_boundary
Revises: 0001_initial
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_provider_boundary"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("credential_ref", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("base_url", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "provider_budget_limits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=200), nullable=False),
        sa.Column("limit_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "provider_id", "scope_key", name="uq_provider_budget_scope"),
    )

    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_key", sa.String(length=160), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("credential_ref", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("confirmed_cost_usd", sa.Float(), nullable=True),
        sa.Column("billing_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key", name="uq_usage_records_request_key"),
    )
    op.create_index("ix_usage_records_request_key", "usage_records", ["request_key"], unique=True)
    op.create_index("ix_usage_records_provider_id", "usage_records", ["provider_id"], unique=False)
    op.create_index("ix_usage_records_created_at", "usage_records", ["created_at"], unique=False)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "task_transitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=False),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_task_transition_key"),
    )
    op.create_index("ix_task_transitions_task_id", "task_transitions", ["task_id"], unique=False)
    op.create_index("ix_task_transitions_created_at", "task_transitions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_transitions_created_at", table_name="task_transitions")
    op.drop_index("ix_task_transitions_task_id", table_name="task_transitions")
    op.drop_table("task_transitions")
    op.drop_table("app_settings")
    op.drop_index("ix_usage_records_created_at", table_name="usage_records")
    op.drop_index("ix_usage_records_provider_id", table_name="usage_records")
    op.drop_index("ix_usage_records_request_key", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_table("provider_budget_limits")
    op.drop_table("provider_configs")

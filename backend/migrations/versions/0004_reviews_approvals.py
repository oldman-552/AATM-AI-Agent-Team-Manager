"""Independent review records and approval gates.

Revision ID: 0004_reviews_approvals
Revises: 0003_task_leases
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_reviews_approvals"
down_revision: Union[str, None] = "0003_task_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_agent_id", sa.String(length=36), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_review_idempotency"),
    )
    op.create_index("ix_review_records_task_id", "review_records", ["task_id"], unique=False)
    op.create_index("ix_review_records_reviewer_agent_id", "review_records", ["reviewer_agent_id"], unique=False)
    op.create_index("ix_review_records_created_at", "review_records", ["created_at"], unique=False)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_kind", "approval_requests", ["kind"], unique=False)
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"], unique=False)
    op.create_index("ix_approval_requests_entity_id", "approval_requests", ["entity_id"], unique=False)
    op.create_index("ix_approval_requests_requested_at", "approval_requests", ["requested_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_approval_requests_requested_at", table_name="approval_requests")
    op.drop_index("ix_approval_requests_entity_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_kind", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_review_records_created_at", table_name="review_records")
    op.drop_index("ix_review_records_reviewer_agent_id", table_name="review_records")
    op.drop_index("ix_review_records_task_id", table_name="review_records")
    op.drop_table("review_records")

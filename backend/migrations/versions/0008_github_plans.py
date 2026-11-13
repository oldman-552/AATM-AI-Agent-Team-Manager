"""Recorded, approval-gated pull-request plans (no execution).

Revision ID: 0008_github_plans
Revises: 0007_task_checkpoints
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_github_plans"
down_revision: Union[str, None] = "0007_task_checkpoints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_pull_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("owner", sa.String(length=39), nullable=False),
        sa.Column("repo", sa.String(length=100), nullable=False),
        sa.Column("base_branch", sa.String(length=121), nullable=False),
        sa.Column("head_branch", sa.String(length=121), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("executed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_github_pull_requests_project_id", "github_pull_requests", ["project_id"], unique=False)
    op.create_index("ix_github_pull_requests_status", "github_pull_requests", ["status"], unique=False)
    op.create_index("ix_github_pull_requests_created_at", "github_pull_requests", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_github_pull_requests_created_at", table_name="github_pull_requests")
    op.drop_index("ix_github_pull_requests_status", table_name="github_pull_requests")
    op.drop_index("ix_github_pull_requests_project_id", table_name="github_pull_requests")
    op.drop_table("github_pull_requests")

"""Project Git workspaces.

Revision ID: 0005_project_workspaces
Revises: 0004_reviews_approvals
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_project_workspaces"
down_revision: Union[str, None] = "0004_reviews_approvals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("root_path", sa.String(length=500), nullable=False),
        sa.Column("workspace_path", sa.String(length=500), nullable=False),
        sa.Column("branch", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_project_workspace_project"),
    )
    op.create_index("ix_project_workspaces_project_id", "project_workspaces", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_project_workspaces_project_id", table_name="project_workspaces")
    op.drop_table("project_workspaces")

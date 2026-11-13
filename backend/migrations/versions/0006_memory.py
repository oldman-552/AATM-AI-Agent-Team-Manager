"""Project-isolated memory with version history.

Revision ID: 0006_memory
Revises: 0005_project_workspaces
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_memory"
down_revision: Union[str, None] = "0005_project_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_memory_project_key"),
    )
    op.create_index("ix_memory_entries_project_id", "memory_entries", ["project_id"], unique=False)
    op.create_index("ix_memory_entries_scope", "memory_entries", ["scope"], unique=False)
    op.create_index("ix_memory_entries_agent_id", "memory_entries", ["agent_id"], unique=False)
    op.create_index("ix_memory_entries_task_id", "memory_entries", ["task_id"], unique=False)

    op.create_table(
        "memory_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["memory_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "version", name="uq_memory_version"),
    )
    op.create_index("ix_memory_versions_entry_id", "memory_versions", ["entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_versions_entry_id", table_name="memory_versions")
    op.drop_table("memory_versions")
    op.drop_index("ix_memory_entries_task_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_scope", table_name="memory_entries")
    op.drop_index("ix_memory_entries_project_id", table_name="memory_entries")
    op.drop_table("memory_entries")

"""Browser profile registry with isolated directories.

Revision ID: 0011_browser_profiles
Revises: 0010_agent_permissions
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_browser_profiles"
down_revision: Union[str, None] = "0010_agent_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "browser_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("isolation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_state", sa.String(length=32), nullable=False),
        sa.Column("profile_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_browser_profiles_name", "browser_profiles", ["name"], unique=True)
    op.create_index("ix_browser_profiles_agent_id", "browser_profiles", ["agent_id"], unique=False)
    op.create_index("ix_browser_profiles_status", "browser_profiles", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_browser_profiles_status", table_name="browser_profiles")
    op.drop_index("ix_browser_profiles_agent_id", table_name="browser_profiles")
    op.drop_index("ix_browser_profiles_name", table_name="browser_profiles")
    op.drop_table("browser_profiles")

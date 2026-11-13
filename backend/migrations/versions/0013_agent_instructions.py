"""Recorded operator instructions delivered to agents.

Revision ID: 0013_agent_instructions
Revises: 0012_task_cancellation
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_agent_instructions"
down_revision: Union[str, None] = "0012_task_cancellation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_instructions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("issued_by", sa.String(length=120), nullable=False, server_default="local-user"),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_instructions_agent_id", "agent_instructions", ["agent_id"])
    op.create_index("ix_agent_instructions_created_at", "agent_instructions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_instructions_created_at", table_name="agent_instructions")
    op.drop_index("ix_agent_instructions_agent_id", table_name="agent_instructions")
    op.drop_table("agent_instructions")

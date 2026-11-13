"""Durable task checkpoints for resuming interrupted work.

Revision ID: 0007_task_checkpoints
Revises: 0006_memory
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_task_checkpoints"
down_revision: Union[str, None] = "0006_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence", name="uq_task_checkpoint_sequence"),
    )
    op.create_index("ix_task_checkpoints_task_id", "task_checkpoints", ["task_id"], unique=False)
    op.create_index("ix_task_checkpoints_created_at", "task_checkpoints", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_checkpoints_created_at", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_task_id", table_name="task_checkpoints")
    op.drop_table("task_checkpoints")

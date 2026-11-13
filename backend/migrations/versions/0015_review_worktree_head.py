"""Bind independent task reviews to the reviewed task-worktree commit.

Revision ID: 0015_review_worktree_head
Revises: 0014_orchestrator_run_lock
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_review_worktree_head"
down_revision: Union[str, None] = "0014_orchestrator_run_lock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("review_records", sa.Column("task_worktree_head", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("review_records", "task_worktree_head")

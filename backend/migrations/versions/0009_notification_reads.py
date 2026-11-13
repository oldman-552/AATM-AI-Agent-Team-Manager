"""Persisted read state for derived notifications.

Revision ID: 0009_notification_reads
Revises: 0008_github_plans
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_notification_reads"
down_revision: Union[str, None] = "0008_github_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("notification_id", sa.String(length=80), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("notification_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_reads")

"""Task cancellation intent fields.

Revision ID: 0012_task_cancellation
Revises: 0011_browser_profiles
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_task_cancellation"
down_revision: Union[str, None] = "0011_browser_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancel_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("cancel_reason")
        batch.drop_column("cancel_requested_at")

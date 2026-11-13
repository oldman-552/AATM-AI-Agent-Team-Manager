"""Task execution leases and retry scheduling.

Revision ID: 0003_task_leases
Revises: 0002_provider_boundary
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_task_leases"
down_revision: Union[str, None] = "0002_provider_boundary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("lease_owner", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_tasks_lease_owner", ["lease_owner"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_lease_owner")
        batch.drop_column("next_attempt_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_owner")

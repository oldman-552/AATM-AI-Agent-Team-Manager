"""Add cross-process mutable-workspace dispatch-group leases.

Revision ID: 0017_dispatch_group_leases
Revises: 0016_distributed_worker_slots
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_dispatch_group_leases"
down_revision: Union[str, None] = "0016_distributed_worker_slots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_dispatch_group_leases",
        sa.Column("group_key", sa.String(length=200), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("group_key"),
    )
    op.create_index("ix_orchestrator_dispatch_group_leases_owner", "orchestrator_dispatch_group_leases", ["owner"])
    op.create_index("ix_orchestrator_dispatch_group_leases_expires_at", "orchestrator_dispatch_group_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_orchestrator_dispatch_group_leases_expires_at", table_name="orchestrator_dispatch_group_leases")
    op.drop_index("ix_orchestrator_dispatch_group_leases_owner", table_name="orchestrator_dispatch_group_leases")
    op.drop_table("orchestrator_dispatch_group_leases")

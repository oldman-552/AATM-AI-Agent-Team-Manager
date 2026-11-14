"""Add a fixed pool of database-backed worker permits.

Revision ID: 0016_distributed_worker_slots
Revises: 0015_review_worktree_head
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_distributed_worker_slots"
down_revision: Union[str, None] = "0015_review_worktree_head"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SLOT_CAPACITY = 20


def upgrade() -> None:
    op.create_table(
        "orchestrator_worker_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orchestrator_worker_slots_owner", "orchestrator_worker_slots", ["owner"])
    op.create_index("ix_orchestrator_worker_slots_expires_at", "orchestrator_worker_slots", ["expires_at"])
    op.bulk_insert(
        sa.table("orchestrator_worker_slots", sa.column("id", sa.Integer())),
        [{"id": slot_id} for slot_id in range(1, SLOT_CAPACITY + 1)],
    )


def downgrade() -> None:
    op.drop_index("ix_orchestrator_worker_slots_expires_at", table_name="orchestrator_worker_slots")
    op.drop_index("ix_orchestrator_worker_slots_owner", table_name="orchestrator_worker_slots")
    op.drop_table("orchestrator_worker_slots")

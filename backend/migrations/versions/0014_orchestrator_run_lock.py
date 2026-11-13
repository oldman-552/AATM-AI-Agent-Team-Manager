"""Database-backed expiring lock for orchestrator run requests.

Revision ID: 0014_orchestrator_run_lock
Revises: 0013_agent_instructions
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_orchestrator_run_lock"
down_revision: Union[str, None] = "0013_agent_instructions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_run_locks",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "orchestrator_run_locks",
            sa.column("id", sa.String(length=40)),
            sa.column("owner", sa.String(length=120)),
            sa.column("expires_at", sa.DateTime(timezone=True)),
        ),
        [{"id": "global", "owner": None, "expires_at": None}],
    )


def downgrade() -> None:
    op.drop_table("orchestrator_run_locks")

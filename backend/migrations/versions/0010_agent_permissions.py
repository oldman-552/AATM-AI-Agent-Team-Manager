"""Agent permission scopes.

Revision ID: 0010_agent_permissions
Revises: 0009_notification_reads
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_agent_permissions"
down_revision: Union[str, None] = "0009_notification_reads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows get an empty scope list: deny by default.
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("permissions", sa.JSON(), nullable=True))
    op.execute("UPDATE agents SET permissions = '[]' WHERE permissions IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("permissions")

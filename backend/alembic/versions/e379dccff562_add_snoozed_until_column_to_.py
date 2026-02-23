"""Add snoozed_until column to notifications

Revision ID: e379dccff562
Revises: 032_add_migration_jobs
Create Date: 2026-02-23 19:33:19.205497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e379dccff562'
down_revision: Union[str, Sequence[str], None] = '032_add_migration_jobs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add snoozed_until column to notifications table."""
    op.add_column('notifications', sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove snoozed_until column from notifications table."""
    op.drop_column('notifications', 'snoozed_until')

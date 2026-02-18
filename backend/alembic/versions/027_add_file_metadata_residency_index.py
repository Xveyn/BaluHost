"""Add composite index for ownership residency scanning

This index improves performance when scanning for residency violations
and when querying files by parent_path + owner_id.

Revision ID: 027_residency_index
Revises: 026_fan_schedule
Create Date: 2026-02-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '027_residency_index'
down_revision: Union[str, Sequence[str], None] = '026_fan_schedule'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create composite index on (parent_path, owner_id) for file_metadata."""
    op.create_index(
        'ix_file_metadata_parent_path_owner_id',
        'file_metadata',
        ['parent_path', 'owner_id'],
    )


def downgrade() -> None:
    """Drop composite index."""
    op.drop_index('ix_file_metadata_parent_path_owner_id', table_name='file_metadata')

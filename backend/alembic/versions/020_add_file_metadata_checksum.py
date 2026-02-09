"""Add checksum column to file_metadata

Store SHA-256 checksums alongside file metadata so that duplicate
detection can compare content hashes in addition to path + size.

Revision ID: 020_checksum
Revises: 019_size_bigint
Create Date: 2026-02-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_checksum'
down_revision: Union[str, None] = '019_size_bigint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'file_metadata',
        sa.Column('checksum', sa.String(64), nullable=True),
    )
    op.create_index(
        'ix_file_metadata_checksum',
        'file_metadata',
        ['checksum'],
    )


def downgrade() -> None:
    op.drop_index('ix_file_metadata_checksum', table_name='file_metadata')
    op.drop_column('file_metadata', 'checksum')

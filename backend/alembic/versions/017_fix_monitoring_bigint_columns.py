"""Fix monitoring byte columns to BigInteger

Migration 004 created baluhost_memory_bytes as INTEGER, which overflows
on PostgreSQL when values exceed 2.1 billion (2 GB). This migration
ensures all byte-valued columns are BIGINT.

ALTER COLUMN ... TYPE BIGINT is a no-op if the column is already BIGINT,
so this is safe to run on any installation.

Revision ID: 017_fix_bigint
Revises: 016_energy_price
Create Date: 2026-02-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017_fix_bigint'
down_revision: Union[str, None] = '016_energy_price'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Alter byte columns to BigInteger where they may be INTEGER."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # memory_samples: all byte columns
        op.alter_column('memory_samples', 'used_bytes',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=False)
        op.alter_column('memory_samples', 'total_bytes',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=False)
        op.alter_column('memory_samples', 'available_bytes',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=True)
        op.alter_column('memory_samples', 'baluhost_memory_bytes',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=True)

        # network_samples: byte counters
        op.alter_column('network_samples', 'bytes_sent',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=True)
        op.alter_column('network_samples', 'bytes_received',
                        type_=sa.BigInteger(), existing_type=sa.Integer(),
                        existing_nullable=True)


def downgrade() -> None:
    """No downgrade — shrinking columns risks data loss."""
    pass

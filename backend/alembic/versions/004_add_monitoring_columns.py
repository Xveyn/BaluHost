"""Add new monitoring columns for CPU and Memory

Adds:
- thread_count, p_core_count, e_core_count to cpu_samples
- baluhost_memory_bytes to memory_samples

Revision ID: 004_monitoring_columns
Revises: 003_add_monitoring_tables
Create Date: 2026-01-24
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004_monitoring_columns'
down_revision = '003_monitoring'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to cpu_samples
    with op.batch_alter_table('cpu_samples', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thread_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('p_core_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('e_core_count', sa.Integer(), nullable=True))

    # Add new column to memory_samples
    with op.batch_alter_table('memory_samples', schema=None) as batch_op:
        batch_op.add_column(sa.Column('baluhost_memory_bytes', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    # Remove columns from memory_samples
    with op.batch_alter_table('memory_samples', schema=None) as batch_op:
        batch_op.drop_column('baluhost_memory_bytes')

    # Remove columns from cpu_samples
    with op.batch_alter_table('cpu_samples', schema=None) as batch_op:
        batch_op.drop_column('e_core_count')
        batch_op.drop_column('p_core_count')
        batch_op.drop_column('thread_count')

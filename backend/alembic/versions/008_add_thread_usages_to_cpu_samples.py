"""Add thread_usages column to cpu_samples

Adds:
- thread_usages (JSON) to cpu_samples for per-thread CPU usage tracking

Revision ID: 008_thread_usages
Revises: 007_add_fan_control_tables
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers
revision = '008_thread_usages'
down_revision = '007_fan_control'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add thread_usages column to cpu_samples
    with op.batch_alter_table('cpu_samples', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thread_usages', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove thread_usages column from cpu_samples
    with op.batch_alter_table('cpu_samples', schema=None) as batch_op:
        batch_op.drop_column('thread_usages')

"""add cloud_export_jobs table

Revision ID: 73092035312b
Revises: 544bdacaf251
Create Date: 2026-03-29 17:39:43.028024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73092035312b'
down_revision: Union[str, Sequence[str], None] = '544bdacaf251'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cloud_export_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('connection_id', sa.Integer(), nullable=False),
    sa.Column('source_path', sa.String(length=1000), nullable=False),
    sa.Column('is_directory', sa.Boolean(), nullable=False),
    sa.Column('file_name', sa.String(length=500), nullable=False),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('cloud_folder', sa.String(length=500), nullable=False),
    sa.Column('cloud_path', sa.String(length=1000), nullable=True),
    sa.Column('share_link', sa.String(length=2000), nullable=True),
    sa.Column('link_type', sa.String(length=20), nullable=False),
    sa.Column('link_password', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('progress_bytes', sa.BigInteger(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['connection_id'], ['cloud_connections.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cloud_export_jobs_id'), 'cloud_export_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_cloud_export_jobs_user_id'), 'cloud_export_jobs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_cloud_export_jobs_user_id'), table_name='cloud_export_jobs')
    op.drop_index(op.f('ix_cloud_export_jobs_id'), table_name='cloud_export_jobs')
    op.drop_table('cloud_export_jobs')

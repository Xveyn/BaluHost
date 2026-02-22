"""Drop share_links table

Revision ID: b3c4d5e6f7a8
Revises: 143ea37285ad
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = '143ea37285ad'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('share_links')


def downgrade() -> None:
    op.create_table(
        'share_links',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('file_metadata.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('allow_download', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('allow_preview', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('max_downloads', sa.Integer(), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
    )

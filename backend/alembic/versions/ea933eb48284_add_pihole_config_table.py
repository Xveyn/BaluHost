"""add pihole_config table

Revision ID: ea933eb48284
Revises: 035_add_vcl_mode_and_tracking
Create Date: 2026-02-27 13:24:16.896424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea933eb48284'
down_revision: Union[str, Sequence[str], None] = '035_add_vcl_mode_and_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pihole_config table."""
    op.create_table('pihole_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('pihole_url', sa.String(length=500), nullable=True),
        sa.Column('password_encrypted', sa.Text(), nullable=True),
        sa.Column('upstream_dns', sa.String(length=500), nullable=False),
        sa.Column('docker_image_tag', sa.String(length=100), nullable=False),
        sa.Column('web_port', sa.Integer(), nullable=False),
        sa.Column('use_as_vpn_dns', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop pihole_config table."""
    op.drop_table('pihole_config')

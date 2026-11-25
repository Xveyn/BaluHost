"""local_tls_state: Zustand des Plugins local_tls

Revision ID: e5c8a1f3b702
Revises: d4b7e2c9a610
Create Date: 2026-11-25 00:00:00.000000

Eine Zeile mit Anbieter-Token (verschluesselt), zuletzt gesetzter Adresse und
Erneuerungsstatus des Zertifikats.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5c8a1f3b702'
down_revision: Union[str, Sequence[str], None] = 'd4b7e2c9a610'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'local_tls_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_secret', sa.Text(), nullable=True),
        sa.Column('last_ip', sa.String(length=45), nullable=True),
        sa.Column('last_ip_set_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_renew_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_renew_ok', sa.Boolean(), nullable=True),
        sa.Column('last_renew_reason', sa.String(length=500), nullable=True),
        sa.Column('cert_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('cert_not_after', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('local_tls_state')

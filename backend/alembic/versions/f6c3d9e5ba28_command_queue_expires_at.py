"""command queue deadline (#829)

Revision ID: f6c3d9e5ba28
Revises: e5b2c8d4a917
Create Date: 2026-11-12 00:00:00.000000

Frist des wartenden Aufrufers auf jeder Befehlszeile. Der Primary fuehrt eine
`pending`-Zeile nach Ablauf nicht mehr aus, sondern markiert sie als
gescheitert. NULL steht auf Zeilen von vor dieser Migration und auf Zeilen,
die ein noch laufender Prozess mit aelterem Code schreibt; fuer sie gilt ihr
Alter gegen das Standard-Timeout.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6c3d9e5ba28'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8d4a917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'power_commands',
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'gpu_power_commands',
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('gpu_power_commands', 'expires_at')
    op.drop_column('power_commands', 'expires_at')

"""fan identity legacy columns

Revision ID: 193f03f94b4e
Revises: c4b18e9a2f37
Create Date: 2026-09-05 20:40:57.046699

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '193f03f94b4e'
down_revision: Union[str, Sequence[str], None] = 'c4b18e9a2f37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Herkunftsspalten fuer die Umstellung auf stabile Kennungen (#532).
    # Reiner Nachweis, keine Datenmigration hier - die Zuordnung braucht die
    # Hardware der Zielmaschine und laeuft deshalb beim Dienststart (Task 7).
    op.add_column('fan_configs', sa.Column('legacy_fan_id', sa.String(length=100), nullable=True))
    op.add_column('temp_sensor_labels', sa.Column('legacy_sensor_id', sa.String(length=120), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('temp_sensor_labels', 'legacy_sensor_id')
    op.drop_column('fan_configs', 'legacy_fan_id')

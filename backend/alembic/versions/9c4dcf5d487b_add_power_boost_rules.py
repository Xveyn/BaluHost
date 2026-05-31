"""add power_boost_rules table

Revision ID: 9c4dcf5d487b
Revises: a3ef59de2014
Create Date: 2026-05-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c4dcf5d487b'
down_revision: Union[str, Sequence[str], None] = 'a3ef59de2014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "power_boost_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("pattern", sa.String(length=200), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("target_max_mhz", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_power_boost_rules_id", "power_boost_rules", ["id"])
    op.execute(
        "INSERT INTO power_boost_rules (kind, pattern, label, target_max_mhz, enabled) "
        "VALUES ('game_session', NULL, 'Steam/Proton-Spielsitzung', NULL, true)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_power_boost_rules_id", table_name="power_boost_rules")
    op.drop_table("power_boost_rules")

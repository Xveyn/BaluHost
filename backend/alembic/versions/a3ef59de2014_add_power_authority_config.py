"""add power_authority_config table

Revision ID: a3ef59de2014
Revises: b48340a96a5a
Create Date: 2026-05-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3ef59de2014'
down_revision: Union[str, Sequence[str], None] = 'b48340a96a5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "power_authority_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_authority_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("boost_rules_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ppd_prev_active", sa.Boolean(), nullable=True),
        sa.Column("ppd_prev_enabled", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("INSERT INTO power_authority_config (id, external_authority_enabled, boost_rules_enabled) VALUES (1, false, true)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("power_authority_config")

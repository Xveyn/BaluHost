"""Rename update channel 'beta' to 'unstable'

Revision ID: 034_rename_beta_to_unstable
Revises: 033_add_fan_curve_profiles
Create Date: 2026-02-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '034_rename_beta_to_unstable'
down_revision: Union[str, Sequence[str], None] = '033_add_fan_curve_profiles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE update_config SET channel = 'unstable' WHERE channel = 'beta'")


def downgrade() -> None:
    op.execute("UPDATE update_config SET channel = 'beta' WHERE channel = 'unstable'")

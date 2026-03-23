"""Add wol_mac_address to server_profiles

Revision ID: 047_wol_mac_server_profiles
Revises: 046_fritzbox_config
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "047_wol_mac_server_profiles"
down_revision: Union[str, None] = "046_fritzbox_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "server_profiles",
        sa.Column("wol_mac_address", sa.String(17), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_profiles", "wol_mac_address")

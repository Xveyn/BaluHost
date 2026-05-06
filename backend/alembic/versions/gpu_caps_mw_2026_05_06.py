"""add capabilities_json to gpu_power_runtime_state

Revision ID: gpu_caps_mw_2026_05_06
Revises: gpu_power_mw_2026_05_03
Create Date: 2026-05-06

Adds the ``capabilities_json`` column to ``gpu_power_runtime_state`` so the
primary worker can publish hardware-reported GPU capabilities for followers
to read. Without this, ``GpuPowerManagerService.get_capabilities()`` on a
secondary worker returns ``vendor=None`` because its ``_backend`` is ``None``,
and the UI's Hardware Overrides section flickers between "AMD detected" and
"no GPU detected" depending on which worker handled the request.

NB: revision ID kept short (22 chars). ``alembic_version.version_num`` is
VARCHAR(32) and an earlier migration in this series (originally
``2026_05_03_gpu_power_multi_worker``, 34 chars) failed in prod with
``StringDataRightTruncation``.

See docs/superpowers/plans/2026-05-02-gpu-power-manager-multi-worker-fix.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'gpu_caps_mw_2026_05_06'
down_revision: Union[str, Sequence[str], None] = 'gpu_power_mw_2026_05_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    """Idempotent: skip if the column already exists from a prior partial run."""
    bind = op.get_bind()
    if not _column_exists(bind, 'gpu_power_runtime_state', 'capabilities_json'):
        op.add_column(
            'gpu_power_runtime_state',
            sa.Column('capabilities_json', sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, 'gpu_power_runtime_state', 'capabilities_json'):
        op.drop_column('gpu_power_runtime_state', 'capabilities_json')

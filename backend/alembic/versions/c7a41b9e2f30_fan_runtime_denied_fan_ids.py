"""fan_runtime_state.denied_fan_ids fuer die Anzeige je Luefter (#568)

Der Zustand `pwm_control == NO_PERMISSION` lebt im `_fan_cache` des jeweiligen
Uvicorn-Workers, gesetzt wird er aber nur von dem, der schreibt -- also vom
Primary. Ohne eine gemeinsame Zeile melden die drei Follower fuer denselben
Kanal weiter `supported`, und das Badge in der Luefterkarte erscheint und
verschwindet im 5-Sekunden-Poll, je nachdem welcher Worker antwortet.

Dieselbe Loesung wie fuer `has_write_permission` eine Ebene darueber (#552):
der Primary veroeffentlicht, alle lesen von dort.

Revision ID: c7a41b9e2f30
Revises: d1e5a83f47c2
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "c7a41b9e2f30"
down_revision = "d1e5a83f47c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fan_runtime_state",
        sa.Column("denied_fan_ids", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fan_runtime_state", "denied_fan_ids")

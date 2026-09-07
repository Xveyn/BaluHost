"""fan_runtime_state.released_fans -- an die Board-Automatik zurueckgegebene Kanaele (#534)

Ein Kanal, den BaluHost nicht schreiben kann, wird an die Chip-Automatik
zurueckgegeben. Welcher Kanal in welchem Zustand ist, muss jeder Uvicorn-Worker
beantworten koennen: get_status() laeuft in einem beliebigen der vier, und ein
prozesslokaler Besitzzustand lieferte bei dreien davon None -- die Anzeige
flackerte dann genauso wie das Read-Only-Banner vor #552.

Werte: "released" (die Board-Automatik regelt) und "abandoned" (die Rueckgabe
scheiterte oder blieb wirkungslos -- es regelt niemand).

Revision ID: e2f81c4a7b93
Revises: c7a41b9e2f30
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f81c4a7b93"
down_revision = "c7a41b9e2f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fan_runtime_state",
        sa.Column("released_fans", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fan_runtime_state", "released_fans")

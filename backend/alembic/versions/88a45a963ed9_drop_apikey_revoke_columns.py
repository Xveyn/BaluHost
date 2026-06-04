"""drop revoked_at/revocation_reason from api_keys

Revision ID: 88a45a963ed9
Revises: 18003728626b
Create Date: 2026-06-04

Revoking an API key now hard-deletes the row (see
``ApiKeyService.delete_api_key``), so the soft-revoke bookkeeping columns
are no longer written. Drop them. Safe for live PostgreSQL: both columns
are nullable and unused by the time this runs.
"""
from alembic import op
import sqlalchemy as sa

revision = "88a45a963ed9"
down_revision = "18003728626b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_column("revocation_reason")
        batch_op.drop_column("revoked_at")


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("revocation_reason", sa.String(length=255), nullable=True)
        )

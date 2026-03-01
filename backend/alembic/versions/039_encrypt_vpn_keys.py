"""encrypt vpn server and preshared keys at rest

Revision ID: 039_encrypt_vpn_keys
Revises: 038_add_dns_query_tables
Create Date: 2026-03-01 18:00:00.000000

"""
import logging
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = '039_encrypt_vpn_keys'
down_revision: Union[str, Sequence[str], None] = '038_add_dns_query_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_fernet():
    """Return a Fernet cipher if VPN_ENCRYPTION_KEY is set, else None."""
    key = os.environ.get("VPN_ENCRYPTION_KEY", "")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception as exc:
        logger.warning("Could not initialise Fernet cipher: %s", exc)
        return None


def upgrade() -> None:
    """Widen key columns and encrypt existing plaintext values."""

    # 1. Widen columns to accommodate Fernet-encrypted values (~120+ chars)
    #    Using batch mode for SQLite compatibility in tests/dev.
    with op.batch_alter_table("vpn_config") as batch_op:
        batch_op.alter_column(
            "server_private_key",
            type_=sa.String(255),
            existing_type=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("vpn_clients") as batch_op:
        batch_op.alter_column(
            "preshared_key",
            type_=sa.String(255),
            existing_type=sa.String(64),
            existing_nullable=False,
        )

    # 2. Encrypt existing plaintext values (data migration)
    fernet = _get_fernet()
    if fernet is None:
        logger.info(
            "VPN_ENCRYPTION_KEY not set — skipping data encryption of existing "
            "VPN keys.  They will be encrypted on next write."
        )
        return

    conn = op.get_bind()

    # Encrypt vpn_config.server_private_key
    rows = conn.execute(sa.text("SELECT id, server_private_key FROM vpn_config")).fetchall()
    for row in rows:
        row_id, key_value = row
        if not key_value:
            continue
        # Skip values that already look encrypted (Fernet tokens start with 'gAAAAA')
        if key_value.startswith("gAAAAA"):
            continue
        encrypted = fernet.encrypt(key_value.encode()).decode()
        conn.execute(
            sa.text("UPDATE vpn_config SET server_private_key = :val WHERE id = :id"),
            {"val": encrypted, "id": row_id},
        )

    # Encrypt vpn_clients.preshared_key
    rows = conn.execute(sa.text("SELECT id, preshared_key FROM vpn_clients")).fetchall()
    for row in rows:
        row_id, key_value = row
        if not key_value:
            continue
        if key_value.startswith("gAAAAA"):
            continue
        encrypted = fernet.encrypt(key_value.encode()).decode()
        conn.execute(
            sa.text("UPDATE vpn_clients SET preshared_key = :val WHERE id = :id"),
            {"val": encrypted, "id": row_id},
        )

    logger.info("Encrypted existing VPN keys at rest.")


def downgrade() -> None:
    """Decrypt values back to plaintext and shrink columns."""

    fernet = _get_fernet()

    conn = op.get_bind()

    if fernet is not None:
        # Decrypt vpn_config.server_private_key
        rows = conn.execute(sa.text("SELECT id, server_private_key FROM vpn_config")).fetchall()
        for row in rows:
            row_id, key_value = row
            if not key_value:
                continue
            try:
                decrypted = fernet.decrypt(key_value.encode()).decode()
                conn.execute(
                    sa.text("UPDATE vpn_config SET server_private_key = :val WHERE id = :id"),
                    {"val": decrypted, "id": row_id},
                )
            except Exception:
                pass  # Already plaintext

        # Decrypt vpn_clients.preshared_key
        rows = conn.execute(sa.text("SELECT id, preshared_key FROM vpn_clients")).fetchall()
        for row in rows:
            row_id, key_value = row
            if not key_value:
                continue
            try:
                decrypted = fernet.decrypt(key_value.encode()).decode()
                conn.execute(
                    sa.text("UPDATE vpn_clients SET preshared_key = :val WHERE id = :id"),
                    {"val": decrypted, "id": row_id},
                )
            except Exception:
                pass  # Already plaintext

    # Shrink columns back
    with op.batch_alter_table("vpn_config") as batch_op:
        batch_op.alter_column(
            "server_private_key",
            type_=sa.String(64),
            existing_type=sa.String(255),
            existing_nullable=False,
        )

    with op.batch_alter_table("vpn_clients") as batch_op:
        batch_op.alter_column(
            "preshared_key",
            type_=sa.String(64),
            existing_type=sa.String(255),
            existing_nullable=False,
        )

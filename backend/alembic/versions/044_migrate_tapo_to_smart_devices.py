"""Migrate tapo_devices data to smart_devices and power_samples to smart_device_samples.

Copies existing Tapo device entries into the new generic smart_devices table
and converts power_samples into smart_device_samples with JSON data format.

After this migration both old and new tables exist with data in the new tables.
A follow-up migration will drop the old tables.

Revision ID: 044_tapo_migration
Revises: f8c303632ab7
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '044_tapo_migration'
down_revision: Union[str, None] = 'f8c303632ab7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Copy tapo_devices → smart_devices, power_samples → smart_device_samples."""
    conn = op.get_bind()

    # Check if tapo_devices table exists and has data
    inspector = sa.inspect(conn)
    if 'tapo_devices' not in inspector.get_table_names():
        return

    tapo_devices = sa.table(
        'tapo_devices',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('device_type', sa.String),
        sa.column('ip_address', sa.String),
        sa.column('email_encrypted', sa.Text),
        sa.column('password_encrypted', sa.Text),
        sa.column('is_active', sa.Boolean),
        sa.column('is_monitoring', sa.Boolean),
        sa.column('last_connected', sa.DateTime),
        sa.column('last_error', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
        sa.column('created_by_user_id', sa.Integer),
    )

    smart_devices = sa.table(
        'smart_devices',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('plugin_name', sa.String),
        sa.column('device_type_id', sa.String),
        sa.column('address', sa.String),
        sa.column('mac_address', sa.String),
        sa.column('capabilities', sa.JSON),
        sa.column('config_secret', sa.Text),
        sa.column('is_active', sa.Boolean),
        sa.column('is_online', sa.Boolean),
        sa.column('last_seen', sa.DateTime),
        sa.column('last_error', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
        sa.column('created_by_user_id', sa.Integer),
    )

    # --- Step 1: Migrate tapo_devices → smart_devices ---
    rows = conn.execute(sa.select(tapo_devices)).fetchall()

    # Build old_id → new_id mapping (smart_devices may already have rows)
    id_map = {}  # old tapo_device.id → new smart_device.id

    for row in rows:
        # Check if already migrated (by name + address)
        existing = conn.execute(
            sa.select(smart_devices.c.id).where(
                sa.and_(
                    smart_devices.c.name == row.name,
                    smart_devices.c.address == row.ip_address,
                    smart_devices.c.plugin_name == 'tapo_smart_plug',
                )
            )
        ).fetchone()

        if existing:
            id_map[row.id] = existing.id
            continue

        # Build config_secret: the old system stored email_encrypted and
        # password_encrypted separately (both already Fernet-encrypted).
        # The new system stores a single Fernet-encrypted JSON blob.
        # We re-use the already-encrypted values by wrapping them in a JSON
        # envelope. The plugin will handle re-encryption on first use.
        # For the migration, store the raw encrypted values as a JSON string
        # so they can be decrypted and re-encrypted later.
        import json
        config_json = json.dumps({
            "_migrated": True,
            "email_encrypted": row.email_encrypted,
            "password_encrypted": row.password_encrypted,
        })

        # Map device_type to device_type_id
        device_type = row.device_type or "P115"
        device_type_id = f"tapo_{device_type.lower()}"

        result = conn.execute(
            smart_devices.insert().values(
                name=row.name,
                plugin_name='tapo_smart_plug',
                device_type_id=device_type_id,
                address=row.ip_address,
                mac_address=None,
                capabilities='["switch", "power_monitor"]',
                config_secret=config_json,
                is_active=row.is_active and row.is_monitoring,
                is_online=False,
                last_seen=row.last_connected,
                last_error=row.last_error,
                created_at=row.created_at,
                updated_at=row.updated_at,
                created_by_user_id=row.created_by_user_id,
            )
        )
        new_id = result.inserted_primary_key[0]
        id_map[row.id] = new_id

    if not id_map:
        return

    # --- Step 2: Migrate power_samples → smart_device_samples ---
    if 'power_samples' not in inspector.get_table_names():
        return

    power_samples = sa.table(
        'power_samples',
        sa.column('id', sa.Integer),
        sa.column('device_id', sa.Integer),
        sa.column('timestamp', sa.DateTime),
        sa.column('watts', sa.Float),
        sa.column('voltage', sa.Float),
        sa.column('current', sa.Float),
        sa.column('energy_today', sa.Float),
        sa.column('is_online', sa.Boolean),
    )

    smart_device_samples = sa.table(
        'smart_device_samples',
        sa.column('device_id', sa.Integer),
        sa.column('capability', sa.String),
        sa.column('data_json', sa.Text),
        sa.column('timestamp', sa.DateTime),
    )

    # Batch-migrate power_samples for mapped devices
    import json as _json

    batch_size = 1000
    for old_device_id, new_device_id in id_map.items():
        offset = 0
        while True:
            sample_rows = conn.execute(
                sa.select(power_samples)
                .where(power_samples.c.device_id == old_device_id)
                .order_by(power_samples.c.id)
                .limit(batch_size)
                .offset(offset)
            ).fetchall()

            if not sample_rows:
                break

            inserts = []
            for s in sample_rows:
                data = {
                    "current_power": s.watts,
                    "voltage": s.voltage,
                    "current_ma": int((s.current or 0) * 1000) if s.current else None,
                    "energy_today_wh": int((s.energy_today or 0) * 1000) if s.energy_today else None,
                    "is_online": s.is_online if s.is_online is not None else True,
                }
                inserts.append({
                    "device_id": new_device_id,
                    "capability": "power_monitor",
                    "data_json": _json.dumps(data),
                    "timestamp": s.timestamp,
                })

            if inserts:
                conn.execute(smart_device_samples.insert(), inserts)

            offset += batch_size


def downgrade() -> None:
    """Remove migrated data from smart_devices (only migration-created entries)."""
    conn = op.get_bind()

    inspector = sa.inspect(conn)
    if 'smart_devices' not in inspector.get_table_names():
        return

    # Delete only entries that were created by this migration
    # (identified by config_secret containing _migrated flag)
    conn.execute(
        sa.text(
            "DELETE FROM smart_device_samples WHERE device_id IN "
            "(SELECT id FROM smart_devices WHERE config_secret LIKE '%_migrated%')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM smart_devices WHERE config_secret LIKE '%_migrated%'"
        )
    )

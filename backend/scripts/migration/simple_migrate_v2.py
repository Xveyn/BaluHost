#!/usr/bin/env python3
"""
Simple migration script using direct SQL to handle schema differences.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
from app.models import Base
import shutil
from datetime import datetime

SQLITE_URL = "sqlite:///./baluhost.db"
POSTGRES_URL = "postgresql://baluhost:R4yPEofog2YFzY13-Fr5kNKw10TpDEgZbsD8hvdlP6A@localhost:5432/baluhost"

def create_backup(sqlite_path: Path, backup_dir: Path) -> Path:
    """Create a backup of the SQLite database."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"baluhost_backup_{timestamp}.db"

    print(f"Creating backup: {backup_path}")
    shutil.copy2(sqlite_path, backup_path)
    print(f"Backup created: {backup_path.stat().st_size} bytes")

    return backup_path

def main():
    print("=" * 60)
    print("BaluHost: Simple SQLite -> PostgreSQL Migration v2")
    print("=" * 60)

    # Create backup
    sqlite_path = Path("./baluhost.db")
    if not sqlite_path.exists():
        print(f"Error: SQLite database not found: {sqlite_path}")
        return 1

    backup_path = create_backup(sqlite_path, Path("./backups"))
    print()

    # Create engines
    print("Connecting to databases...")
    source_engine = create_engine(SQLITE_URL)
    target_engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    # Test PostgreSQL connection
    try:
        with target_engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"PostgreSQL connected: {version.split(',')[0]}")
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return 1

    print()

    # Create schema in PostgreSQL
    print("Creating PostgreSQL schema...")
    try:
        Base.metadata.create_all(bind=target_engine)
        print("Schema created successfully")
    except Exception as e:
        print(f"Error creating schema: {e}")
        return 1

    print()

    # Migrate data using direct SQL
    print("Migrating data using direct SQL...")

    source_inspector = inspect(source_engine)
    target_inspector = inspect(target_engine)

    # Define migration order (parent tables first)
    table_order = [
        'users',
        'mobile_devices',
        'camera_backups',
        'sync_folders',
        'upload_queue',
        'expiration_notifications',
        'mobile_registration_tokens',
        'file_metadata',
        'share_links',
        'file_shares',
        'audit_logs',
        'backups',
        'vpn_config',
        'vpn_clients',
        'rate_limit_configs',
        'fritzbox_vpn_configs',
        'server_profiles',
        'vpn_profiles',
        'vcl_settings',
        'vcl_stats',
        'vcl_file_versions',
        'version_blobs'
    ]

    # Add any tables not in the order list
    all_source_tables = source_inspector.get_table_names()
    tables = [t for t in table_order if t in all_source_tables]
    tables.extend([t for t in all_source_tables if t not in table_order and t != 'alembic_version'])

    total_rows = 0

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table_name in tables:
            if table_name == 'alembic_version':
                continue

            print(f"\nMigrating table: {table_name}")

            try:
                # Get columns from both databases
                source_cols = {col['name'] for col in source_inspector.get_columns(table_name)}

                if table_name not in target_inspector.get_table_names():
                    print(f"  Warning: Table {table_name} not in target, skipping")
                    continue

                target_cols = {col['name'] for col in target_inspector.get_columns(table_name)}

                # Find common columns
                common_cols = source_cols & target_cols

                if not common_cols:
                    print(f"  Warning: No common columns, skipping")
                    continue

                # Read data from source
                select_cols = ', '.join([f'"{col}"' for col in common_cols])
                result = source_conn.execute(text(f'SELECT {select_cols} FROM "{table_name}"'))
                rows = result.fetchall()
                count = len(rows)

                if count == 0:
                    print(f"  No data to migrate")
                    continue

                print(f"  Found {count} rows, migrating {len(common_cols)} columns")

                # Get column types from target
                target_col_info = {col['name']: col['type'] for col in target_inspector.get_columns(table_name)}

                # Insert into target
                if rows:
                    col_list = ', '.join([f'"{col}"' for col in common_cols])
                    placeholders = ', '.join([f':{col}' for col in common_cols])
                    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

                    batch_size = 100
                    for i in range(0, count, batch_size):
                        batch = rows[i:i + batch_size]
                        # Convert rows to dicts and handle type conversions
                        batch_dicts = []
                        for row in batch:
                            row_dict = {}
                            for col, value in zip(common_cols, row):
                                # Convert SQLite integer booleans to Python booleans
                                if str(target_col_info.get(col)).upper() == 'BOOLEAN' and isinstance(value, int):
                                    value = bool(value)
                                row_dict[col] = value
                            batch_dicts.append(row_dict)

                        target_conn.execute(text(insert_sql), batch_dicts)
                        target_conn.commit()

                        if i + batch_size < count:
                            print(f"  Migrated {i + batch_size}/{count} rows...")

                    print(f"  Successfully migrated {count} rows")
                    total_rows += count

            except Exception as e:
                print(f"  Error migrating {table_name}: {e}")
                print(f"  Continuing with next table...")
                continue

    print()
    print(f"Total rows migrated: {total_rows}")
    print()

    # Verify migration
    print("Verifying migration...")
    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table_name in tables:
            if table_name == 'alembic_version':
                continue

            try:
                if table_name not in target_inspector.get_table_names():
                    continue

                source_result = source_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                source_count = source_result.scalar()

                target_result = target_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                target_count = target_result.scalar()

                if source_count != target_count:
                    print(f"  MISMATCH in {table_name}: source={source_count}, target={target_count}")
                else:
                    print(f"  OK {table_name}: {source_count} rows")

            except Exception as e:
                print(f"  Error verifying {table_name}: {e}")

    source_engine.dispose()
    target_engine.dispose()

    print()
    print("=" * 60)
    print("MIGRATION COMPLETED")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Update backend/.env with:")
    print(f"   DATABASE_URL={POSTGRES_URL}")
    print("2. Set NAS_MODE=prod")
    print("3. Restart BaluHost server")
    print(f"4. Backup saved: {backup_path}")
    return 0

if __name__ == '__main__':
    sys.exit(main())

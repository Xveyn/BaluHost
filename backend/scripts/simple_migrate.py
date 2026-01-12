#!/usr/bin/env python3
"""
Simple migration script that creates PostgreSQL schema and migrates data.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, FileMetadata, AuditLog, ShareLink, FileShare
from app.models import Backup, VPNConfig, VPNClient, MobileDevice, RateLimitConfig
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
    print("BaluHost: Simple SQLite -> PostgreSQL Migration")
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

    # Migrate data
    print("Migrating data...")

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    source_session = SourceSession()
    target_session = TargetSession()

    # Get all tables
    inspector = inspect(source_engine)
    all_tables = inspector.get_table_names()

    # Define migration order (parent tables first, then children)
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
        'vpn_configs',
        'vpn_clients',
        'rate_limit_configs',
        'sync_states',
        'sync_metadata',
        'sync_versions',
        'fritzbox_vpn_configs',
        'servers',
        'vpn_profiles',
        'vcl_clients',
        'vcl_credentials'
    ]

    # Add any tables not in the order list at the end
    tables = [t for t in table_order if t in all_tables]
    tables.extend([t for t in all_tables if t not in table_order and t != 'alembic_version'])

    total_rows = 0

    for table_name in tables:
        if table_name == 'alembic_version':
            continue

        print(f"\nMigrating table: {table_name}")

        # Find model class
        model_class = None
        for cls in Base.__subclasses__():
            if hasattr(cls, '__tablename__') and cls.__tablename__ == table_name:
                model_class = cls
                break

        if not model_class:
            print(f"  Warning: Model class not found for {table_name}, skipping")
            continue

        try:
            # Get columns from source table
            source_inspector = inspect(source_engine)
            source_columns = {col['name'] for col in source_inspector.get_columns(table_name)}

            # Get columns from model
            model_columns = {c.name for c in model_class.__table__.columns}

            # Find common columns
            common_columns = source_columns & model_columns

            if not common_columns:
                print(f"  Warning: No common columns found, skipping")
                continue

            # Read all rows from source
            source_rows = source_session.query(model_class).all()
            count = len(source_rows)

            if count == 0:
                print(f"  No data to migrate")
                continue

            print(f"  Found {count} rows")

            # Insert into target
            for i, row in enumerate(source_rows, 1):
                # Convert to dict, only use columns that exist in source
                row_dict = {}
                for c in row.__table__.columns:
                    if c.name in source_columns:
                        try:
                            row_dict[c.name] = getattr(row, c.name)
                        except:
                            pass

                # Create new instance for target
                new_row = model_class(**row_dict)
                target_session.add(new_row)

                # Commit in batches of 100
                if i % 100 == 0:
                    target_session.commit()
                    print(f"  Migrated {i}/{count} rows...")

            # Final commit
            target_session.commit()
            print(f"  Successfully migrated {count} rows")

            total_rows += count

        except Exception as e:
            target_session.rollback()
            print(f"  Error migrating {table_name}: {e}")
            # Continue with next table instead of aborting
            print(f"  Skipping {table_name} and continuing...")
            continue

    source_session.close()
    target_session.close()

    print()
    print(f"Total rows migrated: {total_rows}")
    print()

    # Verify migration
    print("Verifying migration...")
    source_session = SourceSession()
    target_session = TargetSession()

    all_match = True
    for table_name in tables:
        if table_name == 'alembic_version':
            continue

        try:
            source_count = source_session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar()

            target_count = target_session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar()

            if source_count != target_count:
                print(f"  MISMATCH in {table_name}: source={source_count}, target={target_count}")
                all_match = False
            else:
                print(f"  OK {table_name}: {source_count} rows")
        except:
            pass

    source_session.close()
    target_session.close()

    source_engine.dispose()
    target_engine.dispose()

    print()
    if all_match:
        print("=" * 60)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Update backend/.env with DATABASE_URL")
        print("2. Set NAS_MODE=prod")
        print("3. Restart BaluHost server")
        print(f"4. Backup saved: {backup_path}")
        return 0
    else:
        print("MIGRATION VERIFICATION FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())

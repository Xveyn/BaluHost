#!/usr/bin/env python3
"""
BaluHost: SQLite → PostgreSQL Migration Tool

This script migrates data from SQLite to PostgreSQL with backup and verification.
"""

import sys
import os
from pathlib import Path
import argparse
import shutil
from datetime import datetime
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# Import all models to ensure they're registered
from app.models import Base, User, FileMetadata, AuditLog, ShareLink, FileShare
from app.models import Backup, VPNConfig, VPNClient, MobileDevice, RateLimitConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_backup(sqlite_path: Path, backup_dir: Path) -> Path:
    """Create a backup of the SQLite database."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"baluhost_backup_{timestamp}.db"

    logger.info(f"Creating backup: {backup_path}")
    shutil.copy2(sqlite_path, backup_path)
    logger.info(f"Backup created successfully: {backup_path.stat().st_size} bytes")

    return backup_path


def verify_postgres_connection(postgres_url: str) -> bool:
    """Verify PostgreSQL connection."""
    try:
        logger.info("Testing PostgreSQL connection...")
        engine = create_engine(postgres_url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"PostgreSQL connection successful: {version.split(',')[0]}")
        engine.dispose()
        return True
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return False


def run_migrations(postgres_url: str) -> bool:
    """Run Alembic migrations on PostgreSQL."""
    try:
        logger.info("Running Alembic migrations...")
        import subprocess

        # Set DATABASE_URL environment variable
        env = os.environ.copy()
        env['DATABASE_URL'] = postgres_url

        result = subprocess.run(
            ['alembic', 'upgrade', 'head'],
            env=env,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        if result.returncode == 0:
            logger.info("Migrations completed successfully")
            logger.debug(result.stdout)
            return True
        else:
            logger.error(f"Migration failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        return False


def migrate_table_data(source_engine, target_engine, table_name: str) -> int:
    """Migrate data from one table to another."""
    logger.info(f"Migrating table: {table_name}")

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    source_session = SourceSession()
    target_session = TargetSession()

    try:
        # Get the model class
        model_class = None
        for cls in Base.__subclasses__():
            if hasattr(cls, '__tablename__') and cls.__tablename__ == table_name:
                model_class = cls
                break

        if not model_class:
            logger.warning(f"Model class not found for table: {table_name}")
            return 0

        # Read all rows from source
        source_rows = source_session.query(model_class).all()
        count = len(source_rows)

        if count == 0:
            logger.info(f"  → No data to migrate in {table_name}")
            return 0

        logger.info(f"  → Found {count} rows")

        # Insert into target
        for i, row in enumerate(source_rows, 1):
            # Convert to dict
            row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}

            # Create new instance for target
            new_row = model_class(**row_dict)
            target_session.add(new_row)

            # Commit in batches of 100
            if i % 100 == 0:
                target_session.commit()
                logger.info(f"  → Migrated {i}/{count} rows...")

        # Final commit
        target_session.commit()
        logger.info(f"  ✓ Successfully migrated {count} rows")

        return count

    except Exception as e:
        target_session.rollback()
        logger.error(f"  ✗ Error migrating {table_name}: {e}")
        raise

    finally:
        source_session.close()
        target_session.close()


def verify_migration(source_engine, target_engine) -> bool:
    """Verify that all data was migrated correctly."""
    logger.info("Verifying migration...")

    inspector_source = inspect(source_engine)
    inspector_target = inspect(target_engine)

    source_tables = set(inspector_source.get_table_names())
    target_tables = set(inspector_target.get_table_names())

    # Check if all tables exist in target
    missing_tables = source_tables - target_tables
    if missing_tables:
        logger.error(f"Missing tables in target: {missing_tables}")
        return False

    # Verify row counts
    all_match = True
    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    source_session = SourceSession()
    target_session = TargetSession()

    try:
        for table_name in source_tables:
            # Skip alembic version table
            if table_name == 'alembic_version':
                continue

            source_count = source_session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar()

            target_count = target_session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar()

            if source_count != target_count:
                logger.error(
                    f"Row count mismatch in {table_name}: "
                    f"source={source_count}, target={target_count}"
                )
                all_match = False
            else:
                logger.info(f"  ✓ {table_name}: {source_count} rows")

        return all_match

    finally:
        source_session.close()
        target_session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate BaluHost from SQLite to PostgreSQL"
    )
    parser.add_argument(
        '--sqlite-path',
        type=Path,
        default=Path('./baluhost.db'),
        help='Path to SQLite database (default: ./baluhost.db)'
    )
    parser.add_argument(
        '--postgres-url',
        required=True,
        help='PostgreSQL connection URL (e.g., postgresql://user:pass@localhost:5432/baluhost)'
    )
    parser.add_argument(
        '--backup-dir',
        type=Path,
        default=Path('./backups'),
        help='Directory for SQLite backup (default: ./backups)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup (not recommended)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing migration, do not migrate'
    )

    args = parser.parse_args()

    # Validate SQLite path
    if not args.sqlite_path.exists():
        logger.error(f"SQLite database not found: {args.sqlite_path}")
        return 1

    logger.info("=" * 60)
    logger.info("BaluHost: SQLite → PostgreSQL Migration")
    logger.info("=" * 60)
    logger.info(f"Source: {args.sqlite_path}")
    logger.info(f"Target: {args.postgres_url.split('@')[-1]}")  # Hide credentials
    logger.info("")

    # Step 1: Create backup
    if not args.no_backup and not args.verify_only:
        try:
            backup_path = create_backup(args.sqlite_path, args.backup_dir)
            logger.info("")
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return 1

    # Step 2: Verify PostgreSQL connection
    if not verify_postgres_connection(args.postgres_url):
        return 1
    logger.info("")

    # Create engines
    sqlite_url = f"sqlite:///{args.sqlite_path}"
    source_engine = create_engine(sqlite_url)
    target_engine = create_engine(args.postgres_url, pool_pre_ping=True)

    try:
        if args.verify_only:
            # Verify only
            logger.info("Verification mode: checking existing migration")
            if verify_migration(source_engine, target_engine):
                logger.info("\n✓ Migration verification PASSED")
                return 0
            else:
                logger.error("\n✗ Migration verification FAILED")
                return 1

        # Step 3: Run migrations to create schema
        if not run_migrations(args.postgres_url):
            logger.error("Migration failed. Aborting.")
            return 1
        logger.info("")

        # Step 4: Migrate data table by table
        logger.info("Migrating data...")
        inspector = inspect(source_engine)
        tables = inspector.get_table_names()

        total_rows = 0
        for table_name in tables:
            # Skip alembic version table
            if table_name == 'alembic_version':
                continue

            try:
                count = migrate_table_data(source_engine, target_engine, table_name)
                total_rows += count
            except Exception as e:
                logger.error(f"Failed to migrate {table_name}: {e}")
                logger.error("Migration aborted. PostgreSQL data may be incomplete.")
                return 1

        logger.info("")
        logger.info(f"Total rows migrated: {total_rows}")
        logger.info("")

        # Step 5: Verify migration
        if verify_migration(source_engine, target_engine):
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ MIGRATION COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Test the application with PostgreSQL")
            logger.info("2. Update your .env file with DATABASE_URL")
            logger.info("3. Restart your BaluHost server")
            logger.info(f"4. Keep the backup: {backup_path if not args.no_backup else 'N/A'}")
            logger.info("")
            return 0
        else:
            logger.error("\n✗ MIGRATION VERIFICATION FAILED")
            logger.error("Please review the errors above and try again.")
            return 1

    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        logger.exception("Detailed error:")
        return 1

    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == '__main__':
    sys.exit(main())

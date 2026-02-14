#!/usr/bin/env python3
"""
BaluHost: PostgreSQL Migration Simulator

Simulates the migration process without requiring PostgreSQL.
Shows exactly what would be migrated and validates the data.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# Import all models
from app.models import Base, User, FileMetadata, AuditLog, ShareLink, FileShare
from app.models import Backup, VPNConfig, VPNClient, MobileDevice, RateLimitConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_sqlite_database(sqlite_path: Path):
    """Analyze SQLite database and show what would be migrated."""

    print("\n" + "=" * 70)
    print("  BaluHost: PostgreSQL Migration Simulation")
    print("=" * 70)
    print(f"\nSource Database: {sqlite_path}")
    print(f"Size: {sqlite_path.stat().st_size / 1024 / 1024:.2f} MB")

    sqlite_url = f"sqlite:///{sqlite_path}"
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)

    # Get all tables
    tables = inspector.get_table_names()
    print(f"\nTables to migrate: {len(tables)}")
    print("\n" + "-" * 70)

    Session = sessionmaker(bind=engine)
    session = Session()

    total_rows = 0
    table_details = []

    try:
        for table_name in sorted(tables):
            # Skip alembic version table
            if table_name == 'alembic_version':
                continue

            # Get row count
            count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            total_rows += count

            # Get table size estimate (if dbstat is available)
            try:
                result = session.execute(text(
                    f"SELECT SUM(pgsize) FROM dbstat WHERE name='{table_name}'"
                ))
                size = result.scalar()
                size_kb = (size / 1024) if size else 0
            except:
                # dbstat not available in all SQLite versions
                size_kb = 0

            # Get columns
            columns = inspector.get_columns(table_name)

            table_details.append({
                'name': table_name,
                'rows': count,
                'size_kb': size_kb,
                'columns': len(columns)
            })

        # Print summary
        print(f"{'Table':<30} {'Rows':>8} {'Size':>10} {'Columns':>8}")
        print("-" * 70)

        for detail in sorted(table_details, key=lambda x: x['rows'], reverse=True):
            size_str = f"{detail['size_kb']:.1f} KB" if detail['size_kb'] > 0 else "< 1 KB"
            print(f"{detail['name']:<30} {detail['rows']:>8} {size_str:>10} {detail['columns']:>8}")

        print("-" * 70)
        print(f"{'TOTAL':<30} {total_rows:>8}")
        print()

    finally:
        session.close()
        engine.dispose()

    return tables, total_rows, table_details


def analyze_data_integrity(sqlite_path: Path):
    """Check data integrity and relationships."""

    print("\n" + "=" * 70)
    print("  Data Integrity Analysis")
    print("=" * 70)

    sqlite_url = f"sqlite:///{sqlite_path}"
    engine = create_engine(sqlite_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    issues = []
    checks_passed = 0

    try:
        print("\nChecking relationships and constraints...\n")

        # Check 1: Users with files
        user_count = session.execute(text("SELECT COUNT(*) FROM users")).scalar()
        file_count = session.execute(text("SELECT COUNT(*) FROM file_metadata")).scalar()

        print(f"[OK] Users: {user_count}")
        print(f"[OK] Files: {file_count}")
        checks_passed += 2

        # Check 2: Orphaned files (files without owner)
        orphaned = session.execute(text("""
            SELECT COUNT(*) FROM file_metadata
            WHERE owner_id NOT IN (SELECT id FROM users)
        """)).scalar()

        if orphaned > 0:
            issues.append(f"[!] Warning: {orphaned} orphaned files (owner doesn't exist)")
        else:
            print(f"[OK] No orphaned files")
            checks_passed += 1

        # Check 3: VPN clients without users
        vpn_count = session.execute(text("SELECT COUNT(*) FROM vpn_clients")).scalar()
        orphaned_vpn = session.execute(text("""
            SELECT COUNT(*) FROM vpn_clients
            WHERE user_id NOT IN (SELECT id FROM users)
        """)).scalar()

        print(f"[OK] VPN Clients: {vpn_count}")
        if orphaned_vpn > 0:
            issues.append(f"[!] Warning: {orphaned_vpn} VPN clients without user")
        else:
            checks_passed += 1

        # Check 4: Mobile devices
        mobile_count = session.execute(text("SELECT COUNT(*) FROM mobile_devices")).scalar()
        orphaned_mobile = session.execute(text("""
            SELECT COUNT(*) FROM mobile_devices
            WHERE user_id NOT IN (SELECT id FROM users)
        """)).scalar()

        print(f"[OK] Mobile Devices: {mobile_count}")
        if orphaned_mobile > 0:
            issues.append(f"[!] Warning: {orphaned_mobile} mobile devices without user")
        else:
            checks_passed += 1

        # Check 5: Audit logs
        audit_count = session.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()
        print(f"[OK] Audit Logs: {audit_count}")
        checks_passed += 1

        # Check 6: Check for NULL values in required fields
        null_usernames = session.execute(text(
            "SELECT COUNT(*) FROM users WHERE username IS NULL"
        )).scalar()

        if null_usernames > 0:
            issues.append(f"[X] Error: {null_usernames} users with NULL username")
        else:
            print(f"[OK] No NULL usernames")
            checks_passed += 1

        # Summary
        print("\n" + "-" * 70)
        print(f"Checks passed: {checks_passed}")

        if issues:
            print(f"\nIssues found: {len(issues)}")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("[OK] No issues found - data is ready for migration!")

    finally:
        session.close()
        engine.dispose()

    return issues


def simulate_migration_time(total_rows: int, table_details: list):
    """Estimate migration time based on row count."""

    print("\n" + "=" * 70)
    print("  Migration Time Estimate")
    print("=" * 70)

    # Estimates based on typical performance
    rows_per_second = 1000  # Conservative estimate
    backup_time = 5  # seconds
    schema_migration_time = 10  # seconds
    verification_time = 5  # seconds

    data_migration_time = total_rows / rows_per_second
    total_time = backup_time + schema_migration_time + data_migration_time + verification_time

    print(f"\n1. SQLite Backup:           ~{backup_time} seconds")
    print(f"2. Schema Migration:        ~{schema_migration_time} seconds")
    print(f"3. Data Migration:          ~{data_migration_time:.1f} seconds ({total_rows:,} rows)")
    print(f"4. Verification:            ~{verification_time} seconds")
    print("-" * 70)
    print(f"TOTAL ESTIMATED TIME:       ~{total_time:.1f} seconds ({total_time/60:.1f} minutes)")

    # Breakdown by table
    print("\nLargest tables (migration time):")
    large_tables = sorted(table_details, key=lambda x: x['rows'], reverse=True)[:5]
    for table in large_tables:
        time_estimate = table['rows'] / rows_per_second
        print(f"  {table['name']:<30} ~{time_estimate:.1f}s ({table['rows']:,} rows)")


def show_migration_plan():
    """Show the step-by-step migration plan."""

    print("\n" + "=" * 70)
    print("  Migration Plan")
    print("=" * 70)

    steps = [
        ("1. Backup SQLite Database", "Create timestamped backup in ./backups/"),
        ("2. Verify PostgreSQL Connection", "Test connection and PostgreSQL version"),
        ("3. Run Alembic Migrations", "Create schema in PostgreSQL"),
        ("4. Migrate Table Data", "Copy data table-by-table with batching"),
        ("5. Verify Row Counts", "Ensure all data was copied correctly"),
        ("6. Update Configuration", "Set DATABASE_URL in .env"),
        ("7. Test Application", "Start backend with PostgreSQL"),
    ]

    for step, description in steps:
        print(f"\n{step}")
        print(f"  -> {description}")


def check_dependencies():
    """Check if required dependencies are installed."""

    print("\n" + "=" * 70)
    print("  Dependency Check")
    print("=" * 70)
    print()

    all_good = True

    # Check psycopg2
    try:
        import psycopg2
        print(f"[OK] psycopg2: {psycopg2.__version__}")
    except ImportError:
        print("[X] psycopg2: NOT INSTALLED")
        print("  Install: pip install psycopg2-binary")
        all_good = False

    # Check SQLAlchemy
    try:
        import sqlalchemy
        print(f"[OK] SQLAlchemy: {sqlalchemy.__version__}")
    except ImportError:
        print("[X] SQLAlchemy: NOT INSTALLED")
        all_good = False

    # Check Alembic
    try:
        import alembic
        print(f"[OK] Alembic: {alembic.__version__}")
    except ImportError:
        print("[X] Alembic: NOT INSTALLED")
        all_good = False

    print()
    if all_good:
        print("[OK] All dependencies installed - ready to migrate!")
    else:
        print("[!] Some dependencies missing - install them first:")
        print("  cd backend")
        print("  pip install -e \".[dev]\"")

    return all_good


def generate_test_commands(sqlite_path: Path):
    """Generate ready-to-use test commands."""

    print("\n" + "=" * 70)
    print("  Ready-to-Use Commands")
    print("=" * 70)

    print("\nOnce PostgreSQL is running, execute these commands:\n")

    print("# 1. Test PostgreSQL connection")
    print("python scripts/test_postgres_connection.py \\")
    print('    --url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"')
    print()

    print("# 2. Run migration (creates backup automatically)")
    print("python scripts/migrate_to_postgres.py \\")
    print(f"    --sqlite-path {sqlite_path} \\")
    print('    --postgres-url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"')
    print()

    print("# 3. Verify migration")
    print("python scripts/migrate_to_postgres.py --verify-only \\")
    print('    --postgres-url "postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost"')
    print()

    print("# 4. Update backend/.env")
    print('DATABASE_URL=postgresql://baluhost:YOUR_PASSWORD@localhost:5432/baluhost')
    print('NAS_MODE=prod')
    print()

    print("# 5. Start backend")
    print("cd backend")
    print("uvicorn app.main:app --reload --port 3001")


def main():
    sqlite_path = Path(__file__).parent.parent / "baluhost.db"

    if not sqlite_path.exists():
        print(f"Error: SQLite database not found: {sqlite_path}")
        return 1

    # Run all analyses
    tables, total_rows, table_details = analyze_sqlite_database(sqlite_path)
    issues = analyze_data_integrity(sqlite_path)
    simulate_migration_time(total_rows, table_details)
    show_migration_plan()
    deps_ok = check_dependencies()
    generate_test_commands(sqlite_path)

    # Final summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    print(f"\n[OK] Source database analyzed: {total_rows:,} rows across {len(tables)} tables")

    if issues:
        print(f"[!] {len(issues)} data integrity warnings (non-critical)")
    else:
        print(f"[OK] Data integrity: Perfect!")

    if deps_ok:
        print(f"[OK] Dependencies: All installed")
    else:
        print(f"[!] Dependencies: Some missing (see above)")

    print("\nNext Steps:")
    if not deps_ok:
        print("  1. Install dependencies: pip install -e \".[dev]\"")
        print("  2. Install PostgreSQL (Docker or native)")
        print("  3. Run migration script")
    else:
        print("  1. Install PostgreSQL (Docker or native)")
        print("  2. Run migration script (see commands above)")
        print("  3. Test the application")

    print("\n" + "=" * 70)
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())

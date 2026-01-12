#!/usr/bin/env python3
"""Quick PostgreSQL connection test for BaluHost."""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
import argparse


def test_connection(postgres_url: str) -> bool:
    """Test PostgreSQL connection and display info."""
    print("=" * 60)
    print("BaluHost: PostgreSQL Connection Test")
    print("=" * 60)
    print()

    # Redact password for display
    display_url = postgres_url
    if "@" in postgres_url and ":" in postgres_url.split("@")[0]:
        parts = postgres_url.split("@")
        user_pass = parts[0].split("//")[1]
        user = user_pass.split(":")[0]
        display_url = postgres_url.replace(user_pass, f"{user}:***")

    print(f"Testing connection to: {display_url}")
    print()

    try:
        # Create engine
        print("Creating SQLAlchemy engine...")
        engine = create_engine(postgres_url, pool_pre_ping=True)

        # Test connection
        print("Connecting to database...")
        with engine.connect() as conn:
            # Get PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✓ Connection successful!")
            print()
            print(f"PostgreSQL Version:")
            print(f"  {version.split(',')[0]}")
            print()

            # Get database size
            result = conn.execute(text(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ))
            db_size = result.fetchone()[0]
            print(f"Database Size: {db_size}")
            print()

            # List tables
            result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ))
            tables = [row[0] for row in result.fetchall()]

            if tables:
                print(f"Tables ({len(tables)}):")
                for table in tables:
                    # Get row count
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = count_result.scalar()
                    print(f"  - {table:30} ({count:6} rows)")
            else:
                print("No tables found. Run Alembic migrations first:")
                print("  alembic upgrade head")

            print()

            # Connection pool info
            print("Connection Pool:")
            print(f"  Pool Size: {engine.pool.size()}")
            print(f"  Checked Out: {engine.pool.checkedout()}")

        engine.dispose()
        print()
        print("=" * 60)
        print("✓ TEST PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print()
        print("=" * 60)
        print("✗ TEST FAILED")
        print("=" * 60)
        print()
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  1. PostgreSQL not running")
        print("  2. Incorrect credentials")
        print("  3. Database does not exist")
        print("  4. Firewall blocking port 5432")
        print()
        print("Solutions:")
        print("  - Check Docker: docker-compose -f docker-compose.postgres.yml ps")
        print("  - Check credentials in .env.postgres")
        print("  - Verify port: netstat -an | grep 5432")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test PostgreSQL connection")
    parser.add_argument(
        '--url',
        help='PostgreSQL URL (e.g., postgresql://user:pass@localhost:5432/baluhost)'
    )
    args = parser.parse_args()

    # Get URL from argument or environment
    postgres_url = args.url or os.getenv('DATABASE_URL')

    if not postgres_url:
        print("Error: PostgreSQL URL not provided")
        print()
        print("Usage:")
        print("  python test_postgres_connection.py --url postgresql://user:pass@host:port/db")
        print("  or")
        print("  export DATABASE_URL=postgresql://user:pass@host:port/db")
        print("  python test_postgres_connection.py")
        return 1

    if not postgres_url.startswith('postgresql'):
        print(f"Error: Invalid PostgreSQL URL: {postgres_url}")
        print("URL must start with 'postgresql://' or 'postgresql+psycopg2://'")
        return 1

    success = test_connection(postgres_url)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

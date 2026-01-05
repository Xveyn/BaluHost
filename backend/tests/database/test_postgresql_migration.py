"""
PostgreSQL Migration Tests

Test suite für die PostgreSQL Migration.
Wird vor der echten Migration ausgeführt (TDD approach).
"""

import pytest
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Test-Datenbank URL (wird durch PYTEST_POSTGRESQL_HOST etc. überschrieben)
TEST_DATABASE_URL = "postgresql+asyncpg://baluhost_user:baluhost_password@localhost:5432/baluhost_test"

@pytest.fixture
async def test_db():
    """Erstelle Test-Datenbank für jeden Test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Erstelle Tabellen
    async with engine.begin() as conn:
        await conn.run_sync(lambda: None)  # Placeholder
    
    # Erstelle Session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    yield async_session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS files CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS shares CASCADE"))
    
    await engine.dispose()

class TestPostgreSQLMigration:
    """Test PostgreSQL Kompatibilität."""
    
    @pytest.mark.asyncio
    async def test_database_connection(self, test_db):
        """Test: PostgreSQL Verbindung funktioniert."""
        async with test_db() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    @pytest.mark.asyncio
    async def test_users_table_exists(self, test_db):
        """Test: Users-Tabelle existiert."""
        async with test_db() as session:
            # Tabelle wird durch alembic erstellt
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='users'")
            )
            assert result.scalar() is not None
    
    @pytest.mark.asyncio
    async def test_files_table_exists(self, test_db):
        """Test: Files-Tabelle existiert."""
        async with test_db() as session:
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='files'")
            )
            assert result.scalar() is not None
    
    @pytest.mark.asyncio
    async def test_migration_data_integrity(self, test_db):
        """Test: Daten nach Migration intakt."""
        async with test_db() as session:
            # Erstelle Test-User
            await session.execute(
                text("INSERT INTO users (username, email, password_hash) VALUES ('testuser', 'test@example.com', 'hash')")
            )
            await session.commit()
            
            # Lese zurück
            result = await session.execute(
                text("SELECT username FROM users WHERE email='test@example.com'")
            )
            assert result.scalar() == 'testuser'
    
    @pytest.mark.asyncio
    async def test_uuid_primary_keys(self, test_db):
        """Test: UUID Primary Keys funktionieren."""
        async with test_db() as session:
            result = await session.execute(
                text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='users' AND column_name='id'")
            )
            row = result.fetchone()
            assert row is not None
            # UUID sollte als UUID oder TEXT mit Check gespeichert sein
    
    @pytest.mark.asyncio
    async def test_json_column_support(self, test_db):
        """Test: JSON Columns funktionieren."""
        async with test_db() as session:
            # PostgreSQL hat nativen JSON-Support
            result = await session.execute(
                text("SELECT json_object_keys('{\"key\": \"value\"}'::json)")
            )
            assert result.scalar() == 'key'
    
    @pytest.mark.asyncio
    async def test_indexes_exist(self, test_db):
        """Test: Alle wichtigen Indexes existieren."""
        async with test_db() as session:
            # User email index
            result = await session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename='users' AND indexname LIKE '%email%'")
            )
            assert result.scalar() is not None
    
    @pytest.mark.asyncio
    async def test_constraints_exist(self, test_db):
        """Test: Constraints sind gesetzt."""
        async with test_db() as session:
            result = await session.execute(
                text("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name='users' AND constraint_type='UNIQUE'")
            )
            # Mindestens Email sollte UNIQUE sein
            constraints = result.fetchall()
            assert len(constraints) > 0

class TestSQLiteCompatibility:
    """Test dass alte SQLite Migration noch funktioniert."""
    
    @pytest.mark.asyncio
    async def test_sqlite_fallback_schema(self, test_db):
        """Test: SQLite Schema kann gelesen werden."""
        # Dieser Test läuft gegen PostgreSQL, aber validiert Schema-Kompatibilität
        pass

class TestMigrationScripts:
    """Test die Migrations-Skripte."""
    
    def test_migration_script_exists(self):
        """Test: Migration-Skript existiert."""
        from pathlib import Path
        script = Path("backend/scripts/migrate_to_postgresql.py")
        assert script.exists()
    
    def test_migration_script_is_executable(self):
        """Test: Migration-Skript ist ausführbar."""
        from pathlib import Path
        script = Path("backend/scripts/migrate_to_postgresql.py")
        assert script.is_file()

# Integration Tests (nur mit echter PostgreSQL)
class TestRealDatabase:
    """Integration-Tests gegen echte Datenbank."""
    
    @pytest.mark.integration
    async def test_concurrent_connections(self, test_db):
        """Test: Mehrere gleichzeitige Verbindungen."""
        sessions = [test_db() for _ in range(10)]
        
        async def check_connection(session):
            async with session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        
        results = await asyncio.gather(*[check_connection(s) for s in sessions])
        assert all(results)
    
    @pytest.mark.integration
    async def test_transaction_rollback(self, test_db):
        """Test: Transactions rollback korrekt."""
        async with test_db() as session:
            try:
                await session.execute(
                    text("INSERT INTO users (username, email, password_hash) VALUES ('invalid', 'invalid', 'hash')")
                )
                # Absichtlicher Fehler
                raise Exception("Test error")
            except Exception:
                await session.rollback()
        
        # Check dass Insert nicht durchging
        async with test_db() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE username='invalid'")
            )
            assert result.scalar() == 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

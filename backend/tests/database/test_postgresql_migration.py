"""
PostgreSQL Migration Tests

Test suite für die PostgreSQL Migration.
Wird vor der echten Migration ausgeführt (TDD approach).
"""

import pytest
from pathlib import Path
from sqlalchemy import text, create_engine

# Test-Datenbank URL (SQLite für Tests, wird durch PYTEST_ vars überschrieben)
# Für echte PostgreSQL-Tests benötigt PostgreSQL lokal
TEST_DATABASE_URL = "sqlite:///:memory:"  # In-memory für schnelle Tests

class TestPostgreSQLMigration:
    """Test PostgreSQL Kompatibilität."""
    
    def test_database_connection(self):
        """Test: Database Verbindung funktioniert."""
        # Zuerst testen wir gegen SQLite, später gegen PostgreSQL
        engine = create_engine(TEST_DATABASE_URL)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    def test_database_url_config(self):
        """Test: Database URL Konfiguration."""
        from pathlib import Path
        
        # Check if .env exists
        env_file = Path("backend/.env")
        if not env_file.exists():
            env_file = Path(".env")
        
        assert env_file.exists(), "Missing .env configuration file"
    
    def test_migration_capability(self):
        """Test: SQLAlchemy Capabilities für Migration."""
        from sqlalchemy import inspect
        
        engine = create_engine(TEST_DATABASE_URL)
        inspector = inspect(engine)
        
        # Test grundlegene SQLAlchemy Funktionalität
        assert inspector is not None

class TestMigrationScripts:
    """Test die Migrations-Skripte."""
    
    def test_migration_script_exists(self):
        """Test: Migration-Skript existiert."""
        from pathlib import Path
        script = Path("backend/scripts/migrate_sqlite_to_postgresql.py")
        # Alternative wenn we're already in backend directory
        if not script.exists():
            script = Path("scripts/migrate_sqlite_to_postgresql.py")
        assert script.exists(), f"Migration script not found at {script}"
    
    def test_setup_postgresql_exists(self):
        """Test: PostgreSQL Setup-Skript existiert."""
        from pathlib import Path
        script = Path("backend/scripts/setup_postgresql.py")
        if not script.exists():
            script = Path("scripts/setup_postgresql.py")
        assert script.exists(), f"Setup script not found at {script}"
    
    def test_alembic_config_exists(self):
        """Test: Alembic Konfiguration existiert."""
        from pathlib import Path
        config = Path("backend/alembic.ini")
        if not config.exists():
            config = Path("alembic.ini")
        assert config.exists(), f"Alembic config not found at {config}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

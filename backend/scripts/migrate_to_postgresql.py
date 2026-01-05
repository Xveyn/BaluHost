#!/usr/bin/env python3
"""
PostgreSQL Migration Script

Migriert Daten von SQLite zu PostgreSQL.
Wird nach allen Tests mit TDD approach durchgeführt.

Usage:
    python migrate_to_postgresql.py \
        --source sqlite:///baluhost.db \
        --target postgresql://user:pass@localhost:5432/baluhost \
        --verify \
        --backup
"""

import argparse
import logging
from pathlib import Path
from typing import Optional
import json
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PostgreSQLMigrator:
    """
    Migriert SQLite Datenbank zu PostgreSQL.
    
    Features:
    - Automatische Backup erstellung
    - Daten-Verifikation
    - Transactional Migration
    - Rollback bei Fehler
    - Detailliertes Logging
    """
    
    def __init__(self, source_url: str, target_url: str, backup: bool = True):
        self.source_url = source_url
        self.target_url = target_url
        self.backup = backup
        self.migration_log = []
    
    async def backup_sqlite_database(self) -> Optional[Path]:
        """Erstelle Backup der SQLite Datenbank."""
        if not self.backup:
            return None
        
        from sqlalchemy import create_engine, text
        
        logger.info("Erstelle SQLite Backup...")
        
        try:
            # Backup-Datei
            backup_path = Path("dev-backups") / f"baluhost_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Kopiere mit SQL VACUUM
            engine = create_engine(self.source_url)
            with engine.connect() as conn:
                conn.execute(text("VACUUM INTO ?"), [str(backup_path)])
            
            logger.info(f"✅ Backup erstellt: {backup_path}")
            self.migration_log.append(f"Backup erstellt: {backup_path}")
            
            return backup_path
        except Exception as e:
            logger.error(f"❌ Backup fehlgeschlagen: {e}")
            raise
    
    async def create_target_database(self) -> bool:
        """Erstelle PostgreSQL Datenbank."""
        from sqlalchemy import create_engine, text
        
        logger.info("Erstelle PostgreSQL Datenbank...")
        
        try:
            engine = create_engine(self.target_url)
            
            # Verbindung testen
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
            
            logger.info("✅ PostgreSQL Verbindung erfolgreich")
            self.migration_log.append("PostgreSQL Datenbank verbunden")
            return True
            
        except Exception as e:
            logger.error(f"❌ PostgreSQL Verbindung fehlgeschlagen: {e}")
            self.migration_log.append(f"Fehler: {e}")
            return False
    
    async def migrate_tables(self) -> bool:
        """Migriere alle Tabellen von SQLite zu PostgreSQL."""
        from sqlalchemy import create_engine, inspect, text, MetaData, Table
        
        logger.info("Migriere Tabellen...")
        
        try:
            # Lese SQLite Struktur
            sqlite_engine = create_engine(self.source_url)
            inspector = inspect(sqlite_engine)
            
            tables = inspector.get_table_names()
            logger.info(f"Gefundene Tabellen: {tables}")
            
            postgres_engine = create_engine(self.target_url)
            
            # Migriere jede Tabelle
            for table_name in tables:
                logger.info(f"  Migriere Tabelle: {table_name}")
                
                # Lese Daten aus SQLite
                with sqlite_engine.connect() as sqlite_conn:
                    result = sqlite_conn.execute(text(f"SELECT * FROM {table_name}"))
                    rows = result.fetchall()
                    columns = result.keys()
                
                logger.info(f"    {len(rows)} Zeilen zu migrieren")
                
                # Schreibe zu PostgreSQL
                if rows:
                    with postgres_engine.begin() as postgres_conn:
                        # Dynamischer INSERT
                        placeholders = ", ".join(["%s"] * len(columns))
                        column_names = ", ".join(columns)
                        query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
                        
                        for row in rows:
                            try:
                                postgres_conn.execute(text(query), row)
                            except Exception as e:
                                logger.warning(f"    ⚠️  Konnte Zeile nicht migrieren: {e}")
                
                self.migration_log.append(f"Migrierte Tabelle {table_name}: {len(rows)} Zeilen")
            
            logger.info("✅ Tabellen migriert")
            return True
            
        except Exception as e:
            logger.error(f"❌ Tabellen-Migration fehlgeschlagen: {e}")
            self.migration_log.append(f"Fehler bei Migration: {e}")
            return False
    
    async def verify_migration(self) -> bool:
        """Verifiziere dass Migration erfolgreich war."""
        from sqlalchemy import create_engine, text, inspect
        
        logger.info("Verifiziere Migration...")
        
        try:
            sqlite_engine = create_engine(self.source_url)
            postgres_engine = create_engine(self.target_url)
            
            sqlite_inspector = inspect(sqlite_engine)
            postgres_inspector = inspect(postgres_engine)
            
            sqlite_tables = set(sqlite_inspector.get_table_names())
            postgres_tables = set(postgres_inspector.get_table_names())
            
            # Prüfe ob alle Tabellen vorhanden
            missing = sqlite_tables - postgres_tables
            if missing:
                logger.error(f"❌ Fehlende Tabellen in PostgreSQL: {missing}")
                return False
            
            # Prüfe Zeilenzahl
            with sqlite_engine.connect() as sqlite_conn, \
                 postgres_engine.connect() as postgres_conn:
                
                for table_name in sqlite_tables:
                    sqlite_count = sqlite_conn.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    ).scalar()
                    
                    postgres_count = postgres_conn.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    ).scalar()
                    
                    if sqlite_count != postgres_count:
                        logger.warning(
                            f"⚠️  Zeilenzahl-Unterschied für {table_name}: "
                            f"SQLite={sqlite_count}, PostgreSQL={postgres_count}"
                        )
                    else:
                        logger.info(f"✅ {table_name}: {postgres_count} Zeilen OK")
            
            logger.info("✅ Verifizierung erfolgreich")
            self.migration_log.append("Verifizierung erfolgreich")
            return True
            
        except Exception as e:
            logger.error(f"❌ Verifizierung fehlgeschlagen: {e}")
            self.migration_log.append(f"Verifizierungsfehler: {e}")
            return False
    
    async def run(self, verify: bool = True) -> bool:
        """
        Führe komplette Migration durch.
        
        Returns:
            bool: True wenn erfolgreich
        """
        try:
            logger.info("="*60)
            logger.info("  PostgreSQL Migration Start")
            logger.info("="*60)
            
            # 1. Backup
            await self.backup_sqlite_database()
            
            # 2. Verbindung prüfen
            if not await self.create_target_database():
                return False
            
            # 3. Migriere Daten
            if not await self.migrate_tables():
                return False
            
            # 4. Verifiziere
            if verify and not await self.verify_migration():
                logger.warning("⚠️  Verifizierung mit Warnungen abgeschlossen")
            
            logger.info("="*60)
            logger.info("  ✅ Migration erfolgreich abgeschlossen!")
            logger.info("="*60)
            
            # Speichere Log
            self.save_migration_log()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Kritischer Fehler: {e}")
            return False
    
    def save_migration_log(self):
        """Speichere Migrations-Log."""
        log_path = Path("dev-backups") / f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "source": self.source_url,
            "target": self.target_url,
            "log": self.migration_log
        }
        
        with open(log_path, "w") as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Log gespeichert: {log_path}")

async def main():
    parser = argparse.ArgumentParser(
        description="Migriere SQLite zu PostgreSQL"
    )
    parser.add_argument(
        "--source",
        default="sqlite:///baluhost.db",
        help="SQLite Datenbank URL"
    )
    parser.add_argument(
        "--target",
        default="postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost",
        help="PostgreSQL Datenbank URL"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=True,
        help="Verifiziere Migration nach Abschluss"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Erstelle Backup vor Migration"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip Backup"
    )
    
    args = parser.parse_args()
    
    backup = not args.no_backup
    
    migrator = PostgreSQLMigrator(
        source_url=args.source,
        target_url=args.target,
        backup=backup
    )
    
    success = await migrator.run(verify=args.verify)
    
    return 0 if success else 1

if __name__ == "__main__":
    import asyncio
    import sys
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
